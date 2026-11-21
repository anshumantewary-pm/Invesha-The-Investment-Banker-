# Security

## Accounts

The web platform is a static site. Accounts are stored in the user's browser on their own device:
passwords are kept only as salted SHA-256 hashes and are never sent to a server. This separates
users on a shared computer but is not server-grade authentication.

## Data

All calculations run in the browser (Pyodide). Uploaded files are read locally and never uploaded.

## Reporting a vulnerability

Please open a private security advisory on GitHub rather than a public issue.
