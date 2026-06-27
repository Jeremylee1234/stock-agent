"""iFinD 专题报表 / 智能选股配置。

涨跌停、龙虎榜优先使用 smart_stock_picking（已验证可用）：
  - 涨停: searchstring="涨停"
  - 跌停: searchstring="跌停"
  - 龙虎榜: searchstring="龙虎榜"

data_pool 报表编码需在超级命令中核对后更新（当前为占位）。
"""

# data_pool 报表编码占位
DATA_POOL_REPORTS = {
    "top_list": "p03341",
    "limit_list": "p03341",
    "limit_up_pool": "p03341",
}

SMART_PICKING_QUERIES = {
    "limit_up": "涨停",
    "limit_down": "跌停",
    "top_list": "龙虎榜",
}

# 各报表 functionpara 模板（edate/sdate 由调用方注入）
DATA_POOL_FUNCTIONPARA = {
    "limit_up_pool": {
        "sdate": "{start}",
        "edate": "{end}",
        "xmzt": "全部",
        "jcsslx": "全部",
        "jys": "全部",
    },
}

DEFAULT_OUTPUTPARA = "p03341_f001:Y,p03341_f002:Y,p03341_f003:Y,p03341_f004:Y"
