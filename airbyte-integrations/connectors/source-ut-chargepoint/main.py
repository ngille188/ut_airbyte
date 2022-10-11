#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from source_ut_chargepoint import SourceUtChargepoint

if __name__ == "__main__":
    source = SourceUtChargepoint()
    launch(source, sys.argv[1:])
