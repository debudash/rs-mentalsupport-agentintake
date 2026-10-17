# ID images are never stored; sensitive fields are encrypted in the app

The client PRD's default is "extract, confirm, then purge the image". We go further: the
image is read in memory during one request and never written to disk, a bucket or the
database, so there is nothing to purge and nothing to leak. Confirmed identity details,
the free-text reason and the Safety answer are encrypted per field in the application
(Fernet, key only on the app server), so a database dump or backup alone does not expose
them. We chose this over storing the image in private storage because a retry costs the
Client one more photo, while a stored ID image is the most damaging thing this system
could leak.

## Consequences

The review screen cannot re-read a stored image; the Client re-uploads. Encrypted columns
cannot be searched or sorted, which no feature needs. Key rotation in production belongs
in a key manager.
