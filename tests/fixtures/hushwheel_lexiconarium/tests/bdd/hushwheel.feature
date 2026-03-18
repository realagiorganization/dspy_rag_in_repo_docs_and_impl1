Feature: Hushwheel CLI
  The hushwheel fixture should behave like a small maintained command-line utility
  even though its main purpose is to be a very large retrieval corpus.

  Scenario: Lookup a canonical term
    Given the hushwheel binary has been built
    When I run `hushwheel lookup ember-index`
    Then the command exits successfully
    And stdout contains `category: storm-index`

  Scenario: Explain the archive
    Given the hushwheel binary has been built
    When I run `hushwheel about`
    Then the command exits successfully
    And stdout contains `giant static glossary table`

  Scenario: Reject an incomplete prefix query
    Given the hushwheel binary has been built
    When I run `hushwheel prefix`
    Then the command exits with status `2`
    And stderr contains `prefix requires a PREFIX`

  Scenario: Report aggregate statistics
    Given the hushwheel binary has been built
    When I run `hushwheel stats`
    Then the command exits successfully
    And stdout contains `entries: 4108`
