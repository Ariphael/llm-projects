from typing import Any
from pymongo import MongoClient

import httpx2
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import os
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("MONGODB_URI")

# Initialize MCPServer
mcp = MCPServer("governed_mcp")


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
  # client = MongoClient(DB_URI)
  pass



@mcp.tool()
async def get_record(doc_id: str, agent_id: str, roles: list[str]):
  """
  Get the contents of a specific record by id.

  doc_id: ID of document
  agent_id: ID of callee agent
  roles: roles assigned to callee agent
  """
  pass