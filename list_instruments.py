from FinamPy import FinamPy
from FinamPy.grpc.assets.assets_service_pb2 import AssetsRequest

fp = FinamPy()
assets = fp.call_function(fp.assets_stub.Assets, AssetsRequest())

print("Все инструменты:")
for asset in assets.assets[:20]:  # Первые 20
    print(f"  {asset.symbol} - {asset.name}")

fp.close_channel()