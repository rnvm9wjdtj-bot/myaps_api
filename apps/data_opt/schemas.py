# from datetime import datetime
# from typing import Optional, List, Literal
from pydantic import BaseModel#, Field, field_validator

from enum import Enum


class SupplyAction(str, Enum):
    REFRESH_STOCK = 'st.refresh()'
    # OVERWRITE_PLNO = 'pl.overwrite()'

class SupplyOperationBody(BaseModel):
    action: SupplyAction
    # target_row: dict[str, str]  # 目标行数据 {'materialno': '', 'supplyno': ''}
