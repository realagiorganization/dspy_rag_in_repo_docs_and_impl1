Feature: Repository RAG
  Scenario: Answer a repository scope question
    Given the repository root
    When I ask the repository question "What does this repository research?"
    Then the answer mentions "repository"

  Scenario: Discover MCP candidates
    Given the repository root
    When I inspect MCP server candidates
    Then the MCP discovery result is valid JSON

