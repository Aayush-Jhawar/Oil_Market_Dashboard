import asyncio
import json
import websockets

async def listen():
    uri = "ws://localhost:8001/ws"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected. Waiting for snapshot...")
            # Receive one message
            msg = await websocket.recv()
            data = json.loads(msg)
            
            print("\n--- WEBSOCKET SNAPSHOT RECEIVED ---")
            print("Keys in snapshot:", list(data.keys()))
            
            header = data.get("header", {})
            print("\n[Header]")
            print("  Regime:", header.get("regime"))
            print("  Composite Score:", header.get("composite_score"))
            
            regimes = header.get("regimes", {})
            print(f"\n[AI Predictions / Regimes] ({len(regimes)} symbols):")
            for sym, reg in list(regimes.items())[:5]:
                print(f"  {sym}: {reg}")
            if len(regimes) > 5:
                print("  ...")
            
            signals = data.get("signals_by_symbol", {})
            print(f"\n[Signals By Symbol] ({len(signals)} symbols):")
            wti_sig = signals.get("WTI", {})
            print(f"  WTI: Regime={wti_sig.get('regime')} | Signal={wti_sig.get('signal')} | Score={wti_sig.get('composite_score')}")
            brent_sig = signals.get("Brent", {})
            print(f"  Brent: Regime={brent_sig.get('regime')} | Signal={brent_sig.get('signal')} | Score={brent_sig.get('composite_score')}")
            
            paper = data.get("paper", {})
            print("\n[Paper Trading Book]")
            print("  Equity:", paper.get("equity"))
            print("  Open Positions:", len(paper.get("open_positions", [])))
            print("  Closed Trades:", len(paper.get("closed_trades", [])))
            
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    asyncio.run(listen())
