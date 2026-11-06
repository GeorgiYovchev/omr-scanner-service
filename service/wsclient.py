"""Test client: connect to the OMR service and print messages for a while.

  py -3.13 wsclient.py wss://127.0.0.1:8443 60
Set WS_INSECURE=1 to skip certificate/hostname checks (loopback tests of the wildcard cert).
"""
import asyncio, os, ssl, sys, websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8443"
SECS = int(sys.argv[2]) if len(sys.argv) > 2 else 60


def _ssl():
    if not URL.startswith("wss://"):
        return None
    ctx = ssl.create_default_context()
    if os.environ.get("WS_INSECURE") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def main():
    async with websockets.connect(URL, ssl=_ssl()) as ws:
        print("connected to", URL, flush=True)
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=SECS)
                print("RECEIVED:", msg, flush=True)
        except asyncio.TimeoutError:
            print("(no message within window)", flush=True)

asyncio.run(main())
