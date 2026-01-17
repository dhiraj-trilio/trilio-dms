# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 TrilioData, Inc.
# All Rights Reserved.

import pkg_resources

WORKLOADMGR_VENDOR = "TrilioData Inc."
WORKLOADMGR_PRODUCT = "TrilioData Inc."

def version_string():
    try:
        return pkg_resources.get_distribution("trilio-dms").version
    except Exception as ex:
        try:
            return pkg_resources.get_distribution("python3-trilio-dms-el9").version
        except Exception as ex:
            return '1.0.0'
