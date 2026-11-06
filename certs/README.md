# certs/

Put the TLS certificate for the WebSocket here (the service switches to `wss://` automatically):

    certs/fullchain.pem   full chain, PEM
    certs/privkey.pem     private key, PEM (RSA or ECDSA)

OddsTech terminals use the `*.oddstech.net` wildcard (same files as the Linux POS terminals,
`/home/pos/Printer/ssl/oddstech.net/`; canonical copy in `nginx-configurations/letsencrypt/archive/oddstech.net/`
— use the `archive/` files, the `live/` entries are symlinks Windows cannot follow).

`*.pem` files are git-ignored. Never commit a private key.
