---
category: newQuery
---
* The query `cpp/redundant-null-check-simple` has been promoted to Code Scanning. The query finds cases where a pointer is compared to null after it has already been dereferenced. Such comparisons likely indicate a bug at the place where the pointer is dereferenced, or where the pointer is compared to null.

  Note: This query was incorrectly noted as being promoted to Code Scanning in CodeQL version 2.14.6.
