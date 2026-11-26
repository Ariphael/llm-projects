from typing import Any
from pymongo import AsyncMongoClient

import httpx2
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import os, json
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME")

# Initialize MCPServer
mcp = MCPServer("governed_mcp")

# TODO - postgres server logging

@mcp.tool()
async def search_records(query: str, classification: str, agent_id: str, roles: list[str]):
  """
  Search the document store by record keywords, owner id or retention category

  Args:
    query: Search terms or record keywords
    classification: Filter by classification (public, internal or confidential)
    agent_id: ID of callee agent
    roles: roles assigned to callee agent
  """
  client = AsyncMongoClient(DB_URI)
  tool_results = []

  try:
    db = client.get_database(DB_NAME)
    documents = db.get_collection(DB_NAME)

    results = await documents.aggregate([
      {
        "$search": {
          "index": "default",
          "text": {
            "query": query,
            "path": [
              { "value": "record", "boost": 3 },
              "id",
              "metadata.owner",
              "metadata.retention_category",
              "metadata.classification_level.level"
            ]
          }
        }
      },
      {
        "$project": {
          "title": 1,
          "metadata": 1,
          "score": { "$meta": "searchScore" }
        }
      }
    ])

    for doc in results:
      tool_results.append({ "score": doc["score"], "id": doc.get("id"), "metadata": doc.get("metadata") })

    await client.close()
  except Exception as e:
    raise ToolError(f"An error occurred while executing search_records tool: {e}")

  return json.dumps(tool_results, default=str)


@mcp.tool()
async def get_record(doc_id: str, agent_id: str, roles: list[str]):
  """
  Get the contents of a specific record by id.

  doc_id: ID of document
  agent_id: ID of callee agent
  roles: roles assigned to callee agent
  """
  client = AsyncMongoClient(DB_URI)
  tool_result = dict()

  try:
    db = client.get_database(DB_NAME)
    documents = db.get_collection(DB_NAME)

    result = await documents.find_one({ "id": doc_id })
    if result == None:
      raise ToolError(f"Unable to find document with id {doc_id}")

    # TODO - enforce retention category

    metadata = result["metadata"]["classification_level"]
    if metadata["level"] == "internal" and (result["owner"] != agent_id or not (set(roles) & set(metadata["roles"]))):
      raise ToolError(
        f"Insufficient permissions to access internal document {doc_id} - you must be the owner of the document or associated with one of the following roles: {metadata["roles"]}"
      )
    elif metadata["level"] == "confidential" and (result["owner"] != agent_id or agent_id not in metadata["identities"]):
      raise ToolError(
        f"Insufficient permissions to access confidential document {doc_id} - you must be the owner of the document or given permission by the owner to access the document"
      )

    # TODO - redact personal information

    tool_result = result

    await client.close()
  except Exception as e:
    raise ToolError(f"An error occurred while executing get_record tool: {e}")

  return json.dumps(tool_result, default=str)

if __name__ == "__main__":
  mcp.run(transport="stdio")