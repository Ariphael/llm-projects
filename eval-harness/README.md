# Eval harness (Work in Progress)
The goal of this project is to evaluate the prompt, model and schema configuration of a math tutoring webapp (based off my uni capstone, CherryPi) on varying inputs, checking the properties that are satisfied on the output.

# Background
In the CherryPi pipeline, one core problem is multi-validity where most tasks have multiple valid answers. Instead of solely comparing output to expected value where applicable, we also need to check the properties that are satisfied on the output and utilise some quality signal such as an LLM judge or human review. Need a way to track how the results change if we vary the configuration (prompt+model+schema), primarily prompt.