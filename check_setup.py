import opendssdirect as dss
import pandas as pd
import matplotlib
from dss.examples import download_repo_snapshot

print("OpenDSS version:", dss.Basic.Version())
print("pandas:", pd.__version__)
print("matplotlib:", matplotlib.__version__)
print("download_repo_snapshot imported OK")
