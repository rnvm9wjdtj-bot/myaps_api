# coding: utf-8

import json
import hashlib
import requests
from urllib.parse import quote
import os
from typing import Dict, Any, Optional, OrderedDict
from datetime import datetime, timedelta
import time


from ._base import (
    console_log, CACHE_JSON, BaseConnection
)



class JkyConfig():

    BASE_URL = "https://open.jackyun.com/open/openapi/do"
    API_VERSION = "V1.0"
    APP_KEY = CACHE_JSON.get("erp", {}).get("app_key", "")
    APP_SECRET = CACHE_JSON.get("erp", {}).get("app_secret", "")
    """
    ⬆️credential JSON，用于存储吉客云认证信息。文件包含如下结构用于吉客云的认证：
    {
        "erp": {
            "app_key": "...",
            "app_secret": "..."
        }
    }
    """


    PULL_SOURCE :OrderedDict = {
        "全量公司信息": {
            "method": "erp.company.query",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "field_map": {
                "groupId": ["groupId", "group"],
                "currencyCode": ["currencyCode", "currency"],
            },
            "data_node": None
        },

        "全部部门": {
            "method": "erp.depart.query",
            "biz_content": {},
            "data_node": None
        },

        "全部员工": {
            "method": "erp.user.search",
            "biz_content": {
                "cols": "companyId,companyName,email,mainDepartId,mainDepartName,mobile,realName,userId,userName",
                "pageIndex": None,
                "pageSize": None
            },
            "data_node": None
        },

        "全部仓库": {
            "method": "erp.warehouse.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "data_node": "warehouseInfo"
        },

        "全部销售渠道": {
            "method": "erp.sales.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "data_node": "salesChannelInfo"
        },

        "货品全量分类": {
            "method": "erp.goodscate.get",
            "biz_content": {},
            "data_node": None
        },

        "全量物流公司": {
            "method": "erp.logistic.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "data_node": "logisticInfo"
        },

        "全量结算账户": {
            "method": "erp-baseinfo.bankaccounts.listNeed",
            "biz_content": {
                "pageIndex": None,
                "pageSize": None,
                "isIncludeBlockup": 1,
                "cols": "accId,accName,acctypeCode,companyId,companyName,currId,currName,platAccountId,memo,bankCode,bankName,bankbranch,accOwner,accNumber,internationalBankAccount,swiftCode,countriesRegions,personalAuth,imageUpload"
            },
            "data_node": None
        },

        "更新SKU": {
            "method": "erp.storage.goodslist",
            "biz_content": {
                "startDateModifiedSku": None,
                "endDateModifiedSku": None,
                "pageSize": None,
                "pageIndex": None,
                "isQueryDelete": 0,
                "skuIsBlockup": 0,
                "isBlockup": 0,
                "isPackageGood": 0
            },
            "data_node": "goods"
        },

        "更新客户信息": {
            "method": "crm.customer.list",
            "biz_content": {
                "gmtModifiedBegin": None,
                "gmtModifiedEnd": None,
                "pageSize": None,
                "pageIndex": None,
                "hasTotal": 1,
                "enable": 1
            },
            "data_node": None
        },

        "更新JY单": {
            "method": "oms.trade.fullinfoget",
            "biz_content": {
                "startModified": None,
                "endModified": None,
                "pageSize": None,
                "pageIndex": None,
                "hasTotal": 1, 
                "fields": "totalResults,trades,checkTotal,tradeNo,otherFee,chargeCurrency,accountName,payType,payNo,sellerMemo,buyerMemo,goodsDetail,goodsDetail.goodsNo,goodsDetail.goodsName,goodsDetail.specName,goodsDetail.barcode,goodsDetail.sellCount,goodsDetail.unit,goodsDetail.sellPrice,goodsDetail.sellTotal,goodsDetail.cost,goodsDetail.discountTotal,goodsDetail.discountPoint,goodsDetail.taxFee,goodsDetail.shareFavourableFee,goodsDetail.estimateWeight,goodsDetail.goodsMemo,goodsDetail.cateName,goodsDetail.brandName,goodsDetail.goodsTags,goodsDetail.isFit,goodsDetail.isGift,goodsDetail.discountFee,goodsDetail.taxRate,goodsDetail.estimateGoodsVolume,goodsDetail.isPresell,goodsDetail.customerPrice,goodsDetail.customerTotal,goodsDetail.tradeGoodsNo,goodsDetail.tradeGoodsName,goodsDetail.tradeGoodsSpec,goodsDetail.tradeGoodsUnit,goodsDetail.sourceSubtradeNo,goodsDetail.platCode,goodsDetail.platGoodsId,goodsDetail.subTradeId,goodsDetail.goodsDelivery,goodsDelivery.sendCount,goodsDelivery.productionDate,goodsDelivery.expirationDate,goodsDelivery.batchNo,goodsDelivery.expireDate,goodsDelivery.productDate,goodsDetail.platAuthorId,goodsDetail.platAuthorName,goodsDetail.isPlatGift,goodsDetail.goodsPlatDiscountFee,goodsDetail.tradeOrderGoodsDiscountInfoDtoList,tradeOrderGoodsDiscountInfoDtoList.discountFee,tradeOrderGoodsDiscountInfoDtoList.discountName,goodsDetail.shareFavourableAfterFee,goodsDetail.divideSellTotal,goodsDetail.shareOrderDiscountFee,goodsDetail.shareOrderPlatDiscountFee,goodsDetail.sourceTradeNo,goodsDetail.actualSendCount,goodsDetail.platSkuId,goodsDetail.customerTradeNo,goodsDetail.customerSubtradeNo,goodsDetail.PlatCustomData,goodsDetail.assessmentCostLocal,goodsDetail.assessmentGrossProfitLocal,goodsDetail.assessmentGrossProfitPercent,goodsDetail.goodsCompassSourceContentType,goodsDetail.goodsSeller,goodsDetail.inventoryWarehouseId,goodsDetail.inventoryWarehouseName,goodsDetail.specId,goodsDetail.goodsId,goodsDetail.outerId,goodsDetail.apiType,goodsDetail.tradeId,goodsDetail.skuImgUrl,goodsDetail.needProcessCount,goodsDetail.goodsFlagIds,goodsDetail.goodsFlagNames,appendMemo,tradeFrom,register,seller,auditor,reviewer,estimateWeight,packageWeight,tradeCount,goodsTypeCount,freezeReason,abnormalDescription,onlineTradeNo,goodslist,gmtCreate,gmtModified,stockoutNo,confirmTime,departName,lastShipTime,payStatus,chargeCurrencyCode,chargeExchangeRate,tradeStatus,grossProfit,estimateVolume,customerTypeName,customerGradeName,customerTags,customerCode,customerDiscount,specialReminding,blackList,tradeTime,country,state,city,district,town,zip,payTime,countryCode,cityCode,invoiceType,payerName,payerRegno,payerBankAccount,payerPhone,auditTime,payerAddress,invoiceNo,invoiceCode,invoiceStatus,payerBankName,preTypedetail,firstPayment,finalPayment,firstPaytime,finalPaytime,reviewTime,activationTime,customerTotalFee,customerDiscountFee,notifyPickTime,consignTime,orderNo,customerPostFee,shopId,shopName,tradeOrderPayList,customerPayment,companyName,tradeOrderColumnExt,isBillCheck,warehouseCode,warehouseName,logisticName,tradeId,billDate,logisticType,mainPostid,tradeType,totalFee,taxFee,receivedPostFee,discountFee,payment,couponFee,receivedTotal,postFee,isTableSwitch,completeTime,shopcode,signingTime,goodsSerial,otherPaymentFees,tradeOrderGoodsColumnExts,isDelete,localPayment,localExchangeRate,customerAccount,localCurrencyCode,platCompleteTime,buyerOpenUid,tradeOrderAssemblyGoodsDtoList,tradeOrderRefundTime,assemblyGoodsDetail,apiType,logisticCode,agentShopName,tradeStatusExplain,flagIds,flagNames,sysFlagIds,shopTypeCode,sourceAfterNo,ticketCodeList,allCompassSourceContentType,customerName,invoiceAmount,realFee,packageDetail.state,finReceiptTime,extraLogisticNo,warehouseId,id,govSubsidy,pickUpTime,tradeOrderPre,scrollId,chargeType,chargeCurrency,chargeAccount,accountName,payType,payNo,payment,chargeCurrencyCode,chargeExchangeRate,columnExt.tradeId,goodsSerial.subTradeId,goodsSerial.skuId,goodsSerial.serialNo,goodsSerial.serialNo2,expense.expenseFee,expense.expenseItemName,subTradeId,tradeId,tradeOrderAssemblyGoodsDtoList.goodsNo,tradeOrderAssemblyGoodsDtoList.unit,tradeOrderAssemblyGoodsDtoList.specId,tradeOrderAssemblyGoodsDtoList.goodsId,tradeOrderAssemblyGoodsDtoList.tradeId,tradeOrderAssemblyGoodsDtoList.specName,tradeOrderAssemblyGoodsDtoList.goodsName,tradeOrderAssemblyGoodsDtoList.sellCount,tradeOrderAssemblyGoodsDtoList.subTradeId,tradeOrderAssemblyGoodsDtoList.baseUnitSellCount,tradeOrderAssemblyGoodsDtoList.assemblyGoodsDelivery,tradeId,specId,batchNo,expireDate,subTradeId,productDate,packageDetail.state,packageDetail.city,packageDetail.town,packageDetail.district,packageDetail.isGift,packageDetail.barcode,packageDetail.tradeNo,packageDetail.buyerMemo,packageDetail.sellCount,packageDetail.isPlatGift,packageDetail.logisticNo,packageDetail.sellerMemo,packageDetail.consignTime,packageDetail.logisticCode,packageDetail.logisticName,packageDetail.sourceTradeNo,packageDetail.warehouseName,packageDetail.sourceSubtradeNo,frstPaytime,firstPayment,finalPaytime,finalPayment,preTypedetail,sourceTradeNo"
            },
            "data_node": "trades"
        },

        "更新网店订单": {
            "method": "omsapi-business.order.get",
            "biz_content": {
                "startModified": None,
                "endModified": None,
                "pageSize": None,
                "pageIndex": None,
                "hasTotal": 1
            },
            "data_node": None
        },

        "发货单": {
            "method": "wms.order.query-info.page",
            "biz_content": {
                "startModifyTime": None,
                "endModifyTime": None,
                "pageSize": None,
                "pageIndex": None,
                "hasTotal": 1
            },
            "data_node": None
        },
    }



class JkyConnection(BaseConnection):

    def __init__(self, config: JkyConfig=JkyConfig):
        self.config = config
        self.base_url = config.BASE_URL
        self.credential_keys = ("app_key", "app_secret")
        self.app_key = config.APP_KEY
        self.app_secret = config.APP_SECRET
        super().__init__()


    def auth(self):
        pass

    def sign_payload(self, payload: Dict[str, Any]) -> str:
        s = ''
        for k, v in payload.items():
            k = k.strip()
            v = str(v).strip()
            s = f"{s}{k}{v}"

        # s = (app_secret + s + app_secret).lower()
        s = f"{self.app_secret}{s}{self.app_secret}".lower()
        md5_hash = hashlib.md5()
        md5_hash.update(s.encode('utf-8'))
        sign = md5_hash.hexdigest()
        payload['sign'] = sign
        encoded_payload = "&".join(f"{k}={quote(v)}" for k, v in payload.items())
        return encoded_payload


    def call_api(self, base_url, biz_content, method, version, max_retries=3, retry_delay=2, timeout=30) -> Dict[str, Any]:
        
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "appkey": self.app_key,
            "bizcontent": biz_content,
            "contenttype": "json",
            "method": method,
            "timestamp": timestamp,
            "version": version,
        }
        encoded_payload = self.sign_payload(payload)
        url = f"{base_url}?{encoded_payload}"
        headers = {'Content-Type': 'application/json', 'Accept':'application/json'}

        for attempt in range(max_retries):
            try:
                response = self._session.post(url=url, json=payload, headers=headers, timeout=timeout)
                response_json = response.json()
                return response_json
            except requests.exceptions.ChunkedEncodingError as e:
                if attempt < max_retries - 1:
                    console_log.error(f"ChunkedEncodingError occurred (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    console_log.error(f"Timeout occurred (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    console_log.error(f"ConnectionError occurred (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    console_log.error(f"RequestException occurred (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise


    def pull_from_source(self, source_name: str, biz_content_format: Optional[Dict[str, Any]]=None):
        source = self.config.PULL_SOURCE[source_name]
        method = source["method"]
        field_map = source.get("field_map", {})
        biz_content = source["biz_content"]
        if biz_content_format:
            biz_content.update(biz_content_format)
        version = source.get("version", "v1.0")
        data_node = source["data_node"]

        page_size = 200
        page_index = 0
        row_count = 0
        while True:
            page_params = {
                "pageSize": page_size,
                "pageIndex": page_index
            }
            biz_content.update((k, v) for k, v in page_params.items() if k in biz_content)
            response_json = self.call_api(
                base_url=self.base_url,
                biz_content=json.dumps(biz_content),
                method=method,
                version=version
            )
            result_data = response_json['result']['data']
            if data_node:
                result_data = result_data.get(data_node)
            if not result_data:
                break
            data_list = []
            for row in result_data:
                data = {}
                for k, v in row.items():
                    if k in field_map:
                        if isinstance(field_map[k], str):
                            data[field_map[k]] = v
                        else:
                            for f in field_map[k]:
                                data[f] = v
                    else:
                        data[k] = v
                data_list.append(data)
            page_index += 1
            current_page_size = len(result_data)
            row_count += current_page_size
            console_log.info(f"获取【{source_name}】第【{page_index}】页数据，【{current_page_size}】条，累计【{row_count}】条")
            yield data_list
            if current_page_size < page_size or (not "pageSize" in biz_content and page_index > 0):
                break


    def push_into_target(self, *args, **kwargs):
        return super().push_to_target(*args, **kwargs)



# from .hap import HapConfig, HapConnection, Model, StrField, NumField, RelationField, SubtableField, ChoiceField, Q
# from ..utils.hap._base import HapConfig
# from ..utils.hap.connection import HapConnection, AsyncHapConnection
# from ..utils.hap.models import Model
# from ..utils.hap.fields import StrField, NumField, RelationField, SubtableField, ChoiceField
# from ..utils.hap.data_objects import Q

from ..utils.hap import *


ENUM_DECODER = {
    "bankaccounts": {
        "acctypeCode": {
            "PDD": "拼多多",
            "HUIFU": "汇付天下",
            "paypal": "PayPal",
            "WXSP": "微信视频号",
            "SHOPEE": "Shopee",
            "YOUZAN": "有赞",
            "SQB": "收钱吧",
            "LZS": "鹿智深",
            "YMX": "亚马逊",
            "TL": "通联",
            "WFT": "威富通",
            "NNP": "诺诺支付",
            "JD": "京东",
            "ALIPAY": "国际支付宝",
            "tiktok": "tiktok",
            "DEWU": "得物",
            "XHS": "小红书",
            "Lazada": "LaZaDa",
            "FXG": "放心购（抖音小店）",
            "KSXD": "快手小店",
            "KQB": "快钱",
            "THIR": "其他",
            "WECH": "微信",
            "ALIP": "支付宝",
            "BANK": "银行",
            "CASH": "现金"
        }
    },
    "channel": {
        "channelType": {
            "7": "内部交易渠道",
            "6": "加盟门店",
            "5": "分销虚拟店",
            "4": "货主虚拟店",
            "3": "销售办公室",
            "2": "直营门店",
            "1": "直营网店",
            "0": "分销办公室"
        }
    },
    "logistic": {
        "linkType": {
            "2": "自己联系",
            "1": "平台联系"
        }
    },
    "spu": {
        "goodsAttr": {
            "3": "原料",
            "2": "半成品",
            "1": "成品",
            "4": "包装材料",
            "5": "辅料",
            "6": "资产",
            "7": "耗材",
            "8": "服务",
            "9": "设备",
            "10": "备件",
            "11": "费用"
        },
        "ownerType": {
            "0": "自己"
        },
        "imagePosition": {
            "main": "主图",
            "left": "左侧图",
            "right": "右侧图"
        }
    },
    "goodscate": {
        "usableRange": {
            "2": "组合装",
            "1": "单品",
            "0": "全部"
        },
        "imagePosition": {
            "0": "全部",
            "1": "单品",
            "2": "组合装"
        }
    },
    "trade": {
        "tradeStatus": {
            "9090": "已完成",
            "6000": "发货在途",
            "5030": "已取消-被拆分",
            "5020": "已取消-被合并",
            "5010": "已取消",
            "4041": "代销发货已递交",
            "4040": "代销发货待递交",
            "4130": "待发货-部分发货",
            "4123": "待发货-取消失败",
            "4122": "待发货-已取消",
            "4121": "待发货-取消中",
            "4113": "待发货-递交失败",
            "4112": "待发货-已递交",
            "4111": "待发货-递交中",
            "3010": "虚拟发货",
            "2040": "采购等待",
            "2030": "备货等待等生产",
            "2020": "服务等待",
            "2010": "备货等待等补货",
            "2000": "备货等待",
            "1050": "待复核",
            "1030": "预售",
            "1020": "审核中",
            "1010": "待审核"
        },
        "logisticType": {
            "7": "自有物流",
            "6": "线下配送",
            "5": "无需配送",
            "3": "门店配送",
            "2": "上门自提",
            "1": "普通快递"
        },
        "tradeType": {
            "16": "销售对账差异",
            "15": "物流买赔",
            "14": "大B2B业务",
            "13": "销售返利",
            "12": "仅退款",
            "11": "错漏调整",
            "10": "试销业务",
            "9": "批发业务(B2B)",
            "8": "售后退货",
            "7": "售后发货",
            "6": "现款现货",
            "5": "代销售(供货商发货)",
            "2": "代发货（来自分销）",
            "1": "零售业务"
        },
        "payType": {
            "1": "支付宝",
            "2": "财付通",
            "3": "微信支付",
            "4": "银联支付",
            "5": "盛付通",
            "6": "其它",
            "7": "现金",
            "8": "储值卡",
            "9": "扫码付",
            "10": "挂账",
            "11": "诺诺支付",
            "16": "易付宝",
            "27": "通联支付",
            "32": "有赞支付",
            "33": "汇付支付",
            "35": "商盟支付",
            "36": "易宝支付",
            "37": "汇聚支付",
            "38": "合利宝支付"
        },
        "tradeFrom": {
            "1": "网店下载",
            "2": "手工新建",
            "3": "订单导入",
            "4": "吉商城",
            "6": "售后",
            "7": "门店",
            "8": "分销",
            "9": "吉链采购",
            "10": "吉链分销",
            "11": "吉商城分销",
            "12": "奇门分销",
            "13": "销售返利",
            "14": "门店补货"
        },
        "payStatus": {
            "0": "未付款",
            "5": "部分付款",
            "9": "已付款"
        },
        "chargeType": {
            "1": "担保交易",
            "2": "银行收款",
            "3": "现金收款",
            "4": "货到付款",
            "5": "欠款计应收",
            "6": "客户预存款",
            "7": "多种结算",
            "8": "退换货冲抵",
            "9": "电子钱包"
        }
    },
    "customer": {
        "customerCreateSource": {
            "1": "手工新增",
            "2": "Excel导入",
            "3": "吉会员",
            "4": "吉商城:",
            "5": "电商平台",
            "7": "开放平台",
            "8": "销售商机",
            "9": "线下零售",
            "10": "门店注册"
        }
    },
    "": {
        "": {
            "GOODS": "货品资料",
            "SALE_ORDER": "销售订单",
            "CUSTOMER": "客户档案",
            "SUPPLY": "供应商",
            "PURCHASE_ORDER": "采购订单",
            "PURCHASE_RETURN": "采购退货单",
            "OUT_ORDER": "出库单",
            "IN_ORDER": "入库单",
            "ALLOCATE_ORDER": "调拨申请单",
            "DELIVERY_ORDER": "发货单",
            "RECEIVE_ORDER": "收货单",
            "WAVE_BILL": "波次"
        }
    }
}


class Group(Model):
    group_id = StrField(pk=True, field_name="groupId")
    group_name = StrField(field_name="groupName")

    class Meta:
        worksheet_id = "group"
        cache = ["group_id", "group_name"]
        description = "集团"


class Currency(Model):
    currency_code = StrField(pk=True, field_name="currencyCode")
    currency_name = StrField(field_name="currencyName")

    class Meta:
        worksheet_id = "currency"
        cache = ["currency_code", "currency_name"]
        description = "币种"


class Company(Model):
    company_id = StrField(pk=True, field_name="companyId")
    company_code = StrField(field_name="companyCode")
    company_name = StrField(field_name="companyName")
    fax = StrField(field_name="fax")
    tel = StrField(field_name="tel")
    opening_bank = StrField(field_name="openingBank", description="开户行")
    busi_brand = StrField(field_name="busiBrand", description="品牌")
    currency_code = StrField(field_name="currencyCode")
    currency = RelationField(Currency, field_name="currency", follow_with="currency_code")
    currency_name = StrField(field_name="currencyName", description="货币类型名称")
    group_id = StrField(field_name="groupId")
    group = RelationField(Group, field_name="group", follow_with="group_id")
    group_name = StrField(field_name="groupName")

    class Meta:
        worksheet_id = "company"
        cache = ["company_id", "company_code", "company_name"]
        description = "公司"


class BankAccounts(Model):
    acc_id = StrField(pk=True, field_name="accId")
    acc_name = StrField(field_name="accName")
    acctype_code = StrField(field_name="acctypeCode")
    acctype_code__display__ = StrField(field_name="acctypeCode__display__", follow_with="acctype_code", mapper=ENUM_DECODER["bankaccounts"]["acctypeCode"])
    company = RelationField('Company', field_name="company", follow_with="company_id")
    company_id = StrField(field_name="companyId")
    company_name = StrField(field_name="companyName", description="公司名称")
    bank_name = StrField(field_name="bankName", description="开户行")
    acc_owner = StrField(field_name="accOwner", description="户名")
    acc_number = StrField(field_name="accNumber", description="账号")
    currency_id = StrField(field_name="currId")
    currency = RelationField(Currency, field_name="currency", follow_with="currency_id")
    currency_name = StrField(field_name="currName", description="币种名称")
    
    class Meta:
        worksheet_id = "bankaccounts"
        cache = ["acc_id", "acc_name"]
        description = "公司收款账户"


class Department(Model):
    department_id = StrField(pk=True, field_name="departId")
    department_code = StrField(field_name="departCode")
    department_name = StrField(field_name="departName")
    department_type = StrField(field_name="departTypeName", description="部门类型名称")
    user_name = StrField(field_name="userName", description="部门负责人")
    company_id = StrField(field_name="companyId")
    company = RelationField(Company, field_name="company", follow_with="company_id")
    company_code = StrField(field_name="companyCode", description="部门所属公司编码")
    phone = StrField(field_name="departPhone", description="部门电话")
    functional = StrField(field_name="departFunctional", description="部门职能")
    parent_id = StrField(field_name="parentId")
    parent = RelationField('Department', field_name="parent", follow_with="parent_id")
    parent_code = StrField(field_name="parentCode", description="上级部门code")

    class Meta:
        worksheet_id = "depart"
        cache = ["department_id", "department_code", "department_name"]
        description = "部门"


class Staff(Model):
    user_id = StrField(pk=True, field_name="userId")
    is_blockup = NumField(field_name="isBlockup", description="是否停用")
    user_name = StrField(field_name="userName")
    real_name = StrField(field_name="realName", description="真实姓名")
    mobile = StrField(field_name="mobile", description="手机号")
    email = StrField(field_name="email", description="邮箱")
    main_department_id = StrField(field_name="mainDepartId")
    department = RelationField(Department, field_name="department", follow_with="main_department_id")
    main_department_name = StrField(field_name="mainDepartName", description="主部门名称")
    company_id = StrField(field_name="companyId")
    company = RelationField(Company, field_name="company", follow_with="company_id")
    company_name = StrField(field_name="companyName", description="公司名称")

    class Meta:
        worksheet_id = "staff"
        cache = ["user_id", "user_name"]
        description = "员工"


class GoodsCate(Model):
    cate_id = StrField(pk=True, field_name="cateId")
    cate_code = StrField(field_name="cateCode")
    cate_name = StrField(field_name="cateName")
    is_leaf = NumField(field_name="isLeaf", description="是否叶子节点")
    full_name = StrField(field_name="cateFullName", description="分类全路径名称")
    order_index = NumField(field_name="orderIndex", description="序号")
    parent_id = StrField(field_name="parentCateId")
    parent = RelationField('GoodsCate', field_name="parent", follow_with="parent_id")
    usable_range = StrField(field_name="usableRange")
    usable_range_display = StrField(field_name="usableRange__display__", follow_with="usable_range", mapper=ENUM_DECODER["goodscate"]["usableRange"])

    class Meta:
        worksheet_id = "goodscate"
        cache = ["cate_id", "cate_code", "cate_name"]
        description = "货品分类"


class Spu(Model):
    spu_id = StrField(pk=True, field_name="goodsId")
    spu_code = StrField(field_name="goodsNo")
    spu_name = StrField(field_name="goodsName")

    class Meta:
        worksheet_id = "spu"
        cache = ["spu_id", "spu_code", "spu_name"]
        description = "货品"


class Sku(Model):
    sku_id = StrField(pk=True, field_name="skuId")
    sku_code = StrField(field_name="skuNo")
    sku_name = StrField(field_name="skuName")
    barcode = StrField(field_name="skuBarcode", description="条码")
    length = NumField(field_name="skuLength", description="长度")
    width = NumField(field_name="skuWidth", description="宽度")
    height = NumField(field_name="skuHeight", description="高度")
    color_code = StrField(field_name="colorCode", description="颜色编码")
    color_name = StrField(field_name="colorName", description="颜色名称")
    size_code = StrField(field_name="sizeCode", description="尺寸编码")
    size_name = StrField(field_name="sizeName", description="尺寸名称")
    weight = NumField(field_name="skuWeight", description="重量")
    volume = NumField(field_name="skuVolume", description="体积")
    create_time = StrField(field_name="skuGmtCreate", description="创建时间")
    modify_time = StrField(field_name="skuGmtModified", description="修改时间")
    retail_price = NumField(field_name="retailPrice", description="固定成本价")
    memo = StrField(field_name="memo", description="备注")
    is_blockup = NumField(field_name="skuIsBlockup", description="是否停用")
    img_url = StrField(field_name="imgUrl", description="图片URL")
    is_main_image = NumField(field_name="isMainImage", description="是否主图")
    image_position = StrField(field_name="imagePosition", description="图片位置")
    image_position_display = StrField(field_name="imagePosition__display__", follow_with="image_position", mapper=ENUM_DECODER["spu"]["imagePosition"])
    outer_code = StrField(field_name="skuCode", description="外部货品编码")
    goods_no = StrField(field_name="goodsNo", description="货品编号")
    goods_id = StrField(field_name="goodsId", description="货品ID")
    create_time = StrField(field_name="skuGmtCreate", description="创建时间")
    modify_time = StrField(field_name="skuGmtModified", description="修改时间")

    class Meta:
        worksheet_id = "sku"
        cache = ["sku_id", "sku_code", "sku_name"]
        description = "货品规格"


class Warehouse(Model):
    warehouse_id = StrField(pk=True, field_name="warehouseId")
    warehouse_code = StrField(field_name="warehouseCode")
    warehouse_name = StrField(field_name="warehouseName")

    class Meta:
        worksheet_id = "warehouse"
        cache = ["warehouse_id", "warehouse_code", "warehouse_name"]
        description = "仓库"


class Logistic(Model):
    logistic_id = StrField(pk=True, field_name="id")
    logistic_code = StrField(field_name="logisticCode")
    logistic_name = StrField(field_name="logisticName")
    link_man = StrField(field_name="linkMan", description="联系人")
    link_tel = StrField(field_name="linkTel", description="联系电话")
    express_code = StrField(field_name="expressCode", description="快递公司编码")
    express_name = StrField(field_name="expressName", description="快递公司名称")
    link_type = StrField(field_name="linkType", description="联系途径")
    link_type_display = StrField(field_name="linkType__display__", follow_with="link_type", mapper=ENUM_DECODER["logistic"]["linkType"])
    interface_id = StrField(field_name="interfaceId", description="面单接口ID")
    interface_name = StrField(field_name="interfaceName", description="面单接口名称")
    print_template_id = StrField(field_name="printTemplateId", description="打印模板ID")
    print_template_name = StrField(field_name="printTemplateName", description="打印模板名称")
    print_type = StrField(field_name="printType", description="打印类型")

    class Meta:
        worksheet_id = "logistic"
        cache = ["logistic_id", "logistic_code", "logistic_name"]
        description = "物流"


class Channel(Model):
    channel_id = StrField(pk=True, field_name="channelId")
    channel_code = StrField(field_name="channelCode", description="渠道编码")
    channel_name = StrField(field_name="channelName", description="渠道名称")
    channel_type = StrField(field_name="channelType", description="渠道类型")
    channel_type_display = StrField(field_name="channelType__display__", follow_with="channel_type", mapper=ENUM_DECODER["channel"]["channelType"])
    plat_name = StrField(field_name="onlinePlatTypeName", description="店铺平台名称")
    plat_code = StrField(field_name="onlinePlatTypeCode", description="店铺平台编码")
    company_id = StrField(field_name="companyId")
    company = RelationField(Company, field_name="company", follow_with="company_id")
    departnemnt_id = StrField(field_name="channelDepartId")
    department = RelationField(Department, field_name="depart", follow_with="departnemnt_id")

    class Meta:
        worksheet_id = "channel"
        cache = ["channel_id", "channel_code", "channel_name"]
        description = "销售渠道"


class CustomerType(Model):
    type_id = StrField(pk=True, field_name="id")
    type_name = StrField(field_name="name")

    class Meta:
        worksheet_id = "customertype"
        cache = ["type_id", "type_name"]
        description = "客户类别"


class CustomerSource(Model):
    id = StrField(pk=True, field_name="channelCustomerId")
    channel_id = StrField(field_name="channelId")
    channel_relation = RelationField(Channel, field_name="channelId__relation__", follow_with="channel_id")
    salesman_id = StrField(field_name="salesman")
    salesman_relation = RelationField(Staff, field_name="salesman__relation__", follow_with="salesman_id")
    is_default = NumField(field_name="isDefault")

    class Meta:
        worksheet_id = "customerSource"
        description = "客户账号表"


class Customer(Model):
    customer_id = StrField(pk=True, field_name="customerId")
    customer_code = StrField(field_name="customerCode")
    nick_name = StrField(field_name="nickName", description="客户名称")
    alias = StrField(field_name="alias", description="别名")
    type_name = StrField(field_name="customerTypeName", description="客户类别名称")
    debt_max = NumField(field_name="debtAmountMax", description="信用额度")
    debt_amount = NumField(field_name="debtAmount", description="欠款金额")
    default_settlement_name = StrField(field_name="defaultSettlementMethodName", description="默认结算方式名称")
    default_account_name = StrField(field_name="defaultCollectionAccountName", description="默认收款账户名称")
    special_reminding = StrField(field_name="specialReminding", description="特别提醒")
    tag_arr = StrField(field_name="tagArr", description="客户标签")
    create_time = StrField(field_name="gmtCreate", description="创建时间")
    modify_time = StrField(field_name="gmtModified", description="修改时间")
    remark = StrField(field_name="remark", description="备注")
    blacklist = NumField(field_name="blackList", description="是否黑名单")
    no_disturb = NumField(field_name="noDisturb", description="免打扰")
    is_delete = NumField(field_name="isDelete", description="是否删除")
    enable = NumField(field_name="enable", description="是否启用")
    create_source = StrField(field_name="customerCreateSource", description="客户档案创建来源")
    create_source_display = StrField(field_name="customerCreateSource__display__", follow_with="create_source", mapper=ENUM_DECODER["customer"]["customerCreateSource"])
    pre_storage = NumField(field_name="preStorageBalance", description="预存余额")
    logistic_type = StrField(field_name="logisticType", description="默认配送方式")
    default_delivery_logistics = StrField(field_name="defaultDeliveryLogisticsName", description="默认发货物流名称")
    contacts = StrField(field_name="contacts", description="联系人")
    phone = StrField(field_name="phone", description="联系电话")
    detailed_address = StrField(field_name="detailedAddress", description="详细地址")
    customer_type_id = StrField(field_name="customerType")
    customer_type_relation = RelationField(CustomerType, follow_with="customer_type_id", field_name="customerType__relation__")
    salesman_id = StrField(field_name="salesman")
    salesman_relation = RelationField(Staff, field_name="salesman__relation__", follow_with="salesman_id")
    referee_id = StrField(field_name="refereeId")
    referee_relation = RelationField(Staff, field_name="referee__relation__", follow_with="referee_id")
    customer_manager_id = StrField(field_name="customerManager")
    customer_manager_relation = RelationField(Staff, field_name="customerManager__relation__", follow_with="customer_manager_id")
    default_logistics_id = StrField(field_name="defaultDeliveryLogistics", description="默认发货物流id")
    default_logistics_relation = RelationField(Logistic, field_name="defaultDeliveryLogistics__relation__", follow_with="default_logistics_id")
    default_settlement_id = StrField(field_name="defaultSettlementMethod", description="默认结算方式id")
    # default_settlement_method_relation = RelationField(BankAccounts, field_name="defaultSettlementMethod__relation__", follow_with="default_settlement_method_id")
    default_account_id = StrField(field_name="defaultCollectionAccount", description="默认收款账户id")
    # default_account_relation = RelationField(BankAccounts, field_name="defaultCollectionAccount__relation__", follow_with="default_account_id")
    customer_source_arr = StrField(field_name="customerSourceArr")
    customer_source = SubtableField(CustomerSource, field_name="customerSource", data_source="customer_source_arr")

    class Meta:
        worksheet_id = "customer"
        # cache = ["customer_id", "customer_code"]


# class Package(Model):
#     package_id = TextField(pk=True, field_name="packageId")
#     package_code = TextField(field_name="packageNo")
#     package_name = TextField(field_name="packageName")

#     class Meta:
#         worksheet_id = "package"
#         cache = ["package_id", "package_code", "package_name"]


class BusinessOrderGoodsDetail(Model):
    id = StrField(field_name="subTradeId", pk=True)
    trade_no = StrField(field_name="tradeNo", description="网店订单号")
    sub_trade_no = StrField(field_name="subTradeNo", description="网店子单号")

    refund_status = StrField(field_name="refundStatus", description="退款状态")
    status = StrField(field_name="status", description="交易状态")
    is_gift = StrField(field_name="isGift", description="是否赠品")
    good_memo = StrField(field_name="goodsMemo", description="交易备注")
    goods_name = StrField(field_name="goodsName", description="交易名称（平台链接名称）")
    goods_barcode = StrField(field_name="goodsBarcode", description="货品编码（平台SKU码）")
    goods_spec = StrField(field_name="goodsSpec", description="商品交易规格（平台SKU名）")
    sell_count = NumField(field_name="goodsCount", description="货品数量")

    spu_id = StrField(field_name="sysGoodsId", description="系统商品ID（吉客云）")
    spu_relation = RelationField(Spu, follow_with="spu_id", field_name="sysGoodsId__relation__")
    sku_id = StrField(field_name="sysSpecId", description="系统规格ID（吉客云）")
    sku_relation = RelationField(Sku, follow_with="sku_id", field_name="sysSpecId__relation__")

    sell_price = NumField(field_name="sellPrice", description="单价")
    discount_fee = NumField(field_name="discountFee", description="优惠")
    sell_total = NumField(field_name="sellTotal", description="金额")
    palt_logistic_code = StrField(field_name="paltLogisticCode", description="平台指定物流")
    plat_warehouse_code = StrField(field_name="platWarehouseCode", description="平台指定仓库")
    divide_sell_total = NumField(field_name="divideSellTotal", description="实付金额")
    divide_total = NumField(field_name="divideTotal")

    plat_goods_id = StrField(field_name="platGoodsId", description="商品ID（平台链接ID）")
    plat_sku_id = StrField(field_name="platSkuId", description="规格ID（平台SKU ID）")

    plat_parent_order_no = StrField(field_name="platParentOrderNo", description="网店订单ID")

    jky_trade_id = StrField(field_name="tradeId", description="销售单ID")
    jky_trade_relation = RelationField("Trade", follow_with="jky_trade_id", field_name="tradeId__relation__")

    class Meta:
        worksheet_id = "businessOrderGoodsDetail"


class BusinessOrder(Model):
    id = StrField(pk=True, field_name="tradeNo", description="网店订单号")
    sys_flag_ids = StrField(field_name="sysFlagIds", description="订单标记id（平台）")
    trade_status_explain = StrField(field_name="tradeStatusExplain", description="订单状态描述")
    syn_status_explain = StrField(field_name="synStatusExplain", description="发货状态描述")
    cur_status_explain = StrField(field_name="curStatusExplain", description="处理状态描述")
    create_time = StrField(field_name="createTime", description="下单时间")
    pay_time = StrField(field_name="payTime", description="付款时间")
    snd_dead_line = StrField(field_name="sndDeadLine", description="承诺发货时间")
    complete_time = StrField(field_name="completeTime", description="交易完成时间")
    online_modified_time = StrField(field_name="onlineModifiedTime", description="线上修改时间")
    send_time = StrField(field_name="sendTime", description="发货时间")
    gmt_create = StrField(field_name="gmtCreate", description="系统创建时间（吉客云）")
    gmt_modified = StrField(field_name="gmtModified", description="系统修改时间（吉客云）")
    buyer_memo = StrField(field_name="buyerMemo", description="买家备注")
    seller_memo = StrField(field_name="sellerMemo", description="卖家备注")
    plat_coupon_fee = NumField(field_name="platCouponFee", description="平台优惠金额")
    shop_coupon_fee = NumField(field_name="shopCouponFee", description="网店优惠金额")
    total_fee = NumField(field_name="totalFee", description="货款合计")
    payment_fee = NumField(field_name="paymentFee", description="应收合计")
    tax_fee = NumField(field_name="taxFee", description="税额")
    commission_fee = NumField(field_name="commissionFee", description="佣金")
    goods_count = NumField(field_name="goodsCount", description="货品数量")
    pay_no = StrField(field_name="payNo", description="支付单号")

    jky_trade_id = StrField(field_name="sysTradeId_String", description="吉客云销售单ID")
    jky_trade = RelationField("BusinessOrder", follow_with="jky_trade_id", field_name="sysTradeId_String__relation__")
    shop_id = StrField(field_name="shopId")
    shop = RelationField(Channel, follow_with="shop_id", field_name="shopId__relation__")
    shop_name = StrField(field_name="shopName", description="销售渠道")

    goods_detail_json = StrField(field_name="goodsDetailListJson")
    goods_detail_subtable = SubtableField(BusinessOrderGoodsDetail, field_name="goodsDetailList", data_source="goods_detail_json")

    class Meta:
        worksheet_id = "businessOrder"


class TradeGoodsDetail(Model):
    sub_trade_id = StrField(field_name="subTradeId", pk=True)
    source_trade_no = StrField(field_name="sourceTradeNo", description="网店订单号")
    source_sub_trade_no = StrField(field_name="sourceSubtradeNo", description="网店子订单号")
    spec_name = StrField(field_name="specName", description="货品规格名称")
    barcode = StrField(field_name="barcode", description="货品条码")
    unit = StrField(field_name="unit", description="货品单位")
    is_plat_gift = NumField(field_name="isPlatGift", description="是否平台赠品")
    is_presell = NumField(field_name="isPresell", description="是否预售商品")
    sell_price = NumField(field_name="sellPrice", description="单价")
    sell_count = NumField(field_name="sellCount", description="数量")
    sell_total = NumField(field_name="sellTotal", description="总金额")
    discount_point = NumField(field_name="discountPoint", description="抵扣积分")
    discount_total = NumField(field_name="discountTotal", description="抵扣金额")
    is_gift = NumField(field_name="isGift", description="是否赠品")
    api_type = StrField(field_name="apiType", description="渠道类型")
    plat_code = StrField(field_name="platCode", description="平台代码")
    actual_send_count = NumField(field_name="actualSendCount", description="实发数")
    need_process_count = NumField(field_name="needProcessCount", description="需备货数量")
    tax_rate = NumField(field_name="taxRate", description="税率")
    share_favourable_fee = NumField(field_name="shareFavourableFee", description="分摊金额")
    share_favourable_after_fee = NumField(field_name="shareFavourableAfterFee", description="分摊后金额")
    share_order_discount_fee = NumField(field_name="shareOrderDiscountFee", description="分摊后优惠")
    share_order_plat_discount_fee = NumField(field_name="shareOrderPlatDiscountFee", description="分摊后平台补贴")
    customer_price = NumField(field_name="customerPrice", description="终端销售单价")
    customer_total = NumField(field_name="customerTotal", description="终端销售金额")
    plat_custom_data = StrField(field_name="platCustomData", description="平台自定义信息")
    plat_author_id = StrField(field_name="platAuthorId", description="平台主播id")
    plat_author_name = StrField(field_name="platAuthorName", description="平台主播名称")
    goods_compass_source = StrField(field_name="goodsCompassSourceContentType", description="货品级流量题材")
    assessment_cost = NumField(field_name="assessmentCostLocal", description="考核成本")
    assessment_gross = NumField(field_name="assessmentGrossProfitLocal", description="考核毛利")
    assessment_gross_percent = NumField(field_name="assessmentGrossProfitPercent", description="考核毛利率")
    sku_img_url = StrField(field_name="skuImgUrl", description="货品图片url")
    goods_flags = StrField(field_name="goodsFlags", description="货品标记")
    discount_name = StrField(field_name="discountName", description="优惠名称")
    goods_plat_discount_fee = NumField(field_name="goodsPlatDiscountFee", description="货品平台优惠")
    goods_seller = StrField(field_name="goodsSeller", description="货品业务员")

    trade_id = StrField(field_name="tradeId", description="吉客云销售单id")
    order_no = StrField(field_name="orderNo", description="发货单号")

    spu_id = StrField(field_name="goodsId", description="货品id")
    spu = RelationField(Spu, field_name="goodsId__relation__", follow_with="spu_id")
    sku_id = StrField(field_name="specId", description="规格id")
    sku = RelationField(Sku, field_name="specId__relation__", follow_with="sku_id")

    customer_trade_no = StrField(field_name="customerTradeNo", description="终端网店订单号")
    customer_sub_trade_no = StrField(field_name="customerSubtradeNo", description="终端网店子订单号")

    goods_flag_ids = StrField(field_name="goodsFlagIds", description="货品标记id")
    outer_id = StrField(field_name="outerId", description="外部id")
    inventory_warehouse_id = StrField(field_name="inventoryWarehouseId", description="货品逻辑仓id")

    class Meta:
        worksheet_id = "tradeGoodsDetail"


class TradePay(Model):
    charge_account = StrField(field_name="chargeAccount", description="收款帐户")
    account_name = StrField(field_name="accountName", description="收款帐户名称")
    charge_type = StrField(field_name="chargeType", description="结算方式")
    charge_type_display = StrField(field_name="chargeTypeExplain", follow_with="charge_type", mapper=ENUM_DECODER["trade"]["chargeType"])
    pay_type = StrField(field_name="payType", description="支付方式")
    pay_type_display = StrField(field_name="payTypeExplain", follow_with="pay_type", mapper=ENUM_DECODER["trade"]["payType"])
    pay_no = StrField(field_name="payNo", description="支付单号")
    payment = NumField(field_name="payment", description="支付金额")
    currency_code = StrField(field_name="chargeCurrencyCode", description="收款币种")
    currency_relation = RelationField(Currency, field_name="chargeCurrencyCode__relation__", follow_with="currency_code")
    exchange_rate = NumField(field_name="chargeExchangeRate", description="结算汇率")
    trade_id = StrField(field_name="tradeId", description="吉客云销售单id")

    class Meta:
        worksheet_id = "tradePay"


class Trade(Model):
    id = StrField(field_name="Id")
    trade_id = StrField(pk=True, field_name="tradeId")
    jy_no = StrField(field_name="tradeNo")
    trade_status_explain = StrField(field_name="tradeStatusExplain")
    flag_names = ChoiceField(field_name="flagNames", description="订单标记")
    freeze_reason = StrField(field_name="freezeReason", description="订单冻结原因")
    buyer_open_uid = StrField(field_name="buyerOpenUid", description="平台买家唯一标识")
    order_no = StrField(field_name="orderNo", description="发货单单号")
    stockout_no = StrField(field_name="stockoutNo", description="出库单编号")
    online_trade_no = StrField(field_name="onlineTradeNo", description="网店订单号")
    trade_from = StrField(field_name="tradeFrom", description="订单来源")
    trade_from_display = StrField(field_name="tradeFrom__display__", follow_with="trade_from", mapper=ENUM_DECODER["trade"]["tradeFrom"])
    sys_flag_ids = StrField(field_name="sysFlagIds", description="系统标记id")
    shop_type_code = StrField(field_name="shopTypeCode", description="平台类型")
    logistic_name = StrField(field_name="logisticName", description="物流名称")
    main_post_id = StrField(field_name="mainPostid", description="物流单号")
    logistic_type = StrField(field_name="logisticType", description="配送方式")
    logistic_type_display = StrField(field_name="logisticType__display__", follow_with="logistic_type", mapper=ENUM_DECODER["trade"]["logisticType"])
    buyer_memo = StrField(field_name="buyerMemo", description="买家备注")
    seller_memo = StrField(field_name="sellerMemo", description="客服备注")
    append_memo = StrField(field_name="appendMemo", description="追加备注")
    country = StrField(field_name="country", description="国家")
    state = StrField(field_name="state", description="省份")
    city = StrField(field_name="city", description="城市")
    district = StrField(field_name="district", description="区县")
    country_code = StrField(field_name="countryCode", description="国家编码")
    city_code = StrField(field_name="cityCode", description="城市编码")
    town = StrField(field_name="town", description="街道")
    zip_code = StrField(field_name="zip", description="邮政编码")
    goods_type_count = StrField(field_name="goodsTypeCount", description="商品样数")
    trade_type = StrField(field_name="tradeType", description="订单类型")
    trade_type_display = StrField(field_name="tradeType__display__", follow_with="trade_type", mapper=ENUM_DECODER["trade"]["tradeType"])
    company_name = StrField(field_name="companyName", description="公司名称")
    nickname = StrField(field_name="nickname", description="买家昵称")
    charge_type = StrField(field_name="chargeType", description="结算方式")
    charge_type_display = StrField(field_name="chargeType__display__", follow_with="charge_type", mapper=ENUM_DECODER["trade"]["chargeType"])
    charge_currency_code = StrField(field_name="chargeCurrencyCode", description="结算币种编码")
    charge_currency = RelationField(Currency, field_name="chargeCurrencyCode__relation__", follow_with="charge_currency_code")
    pay_status = StrField(field_name="payStatus", description="支付状态")
    pay_status_display = StrField(field_name="payStatus__display__", follow_with="pay_status", mapper=ENUM_DECODER["trade"]["payStatus"])
    pay_type = StrField(field_name="payType", description="支付方式")
    pay_type_display = StrField(field_name="payType__display__", follow_with="pay_type", mapper=ENUM_DECODER["trade"]["payType"])
    pay_no = StrField(field_name="payNo", description="支付单号")
    payment = NumField(field_name="payment", description="支付金额")
    pay_time = StrField(field_name="payTime", description="支付时间")
    check_total = NumField(field_name="checkTotal", description="对账金额")
    gross_profit = NumField(field_name="grossProfit", description="毛利")
    other_fee = NumField(field_name="otherFee", description="其他费用")
    total_fee = NumField(field_name="totalFee", description="商品金额")
    discount_fee = NumField(field_name="discountFee", description="优惠金额")
    local_payment = NumField(field_name="localPayment", description="应收合计")
    received_total = NumField(field_name="receivedTotal", description="已收金额")
    real_fee = NumField(field_name="realFee", description="实付金额")
    invoice_amount = NumField(field_name="invoiceAmount", description="可开票金额")
    tax_fee = NumField(field_name="taxFee", description="税金")
    post_fee = NumField(field_name="postFee", description="邮费")
    received_post_fee = NumField(field_name="receivedPostFee", description="已收邮费")
    estimate_weight = NumField(field_name="estimateWeight", description="估计重量")
    trade_count = NumField(field_name="tradeCount", description="订单数量")
    goods_type_count = NumField(field_name="goodsTypeCount", description="商品样数")
    abnormal_description = StrField(field_name="abnormalDescription", description="问题单具体描述")
    goodslist = StrField(field_name="goodslist", description="货品摘要")
    audit_time = StrField(field_name="auditTime", description="审核时间")
    review_time = StrField(field_name="reviewTime", description="复核时间")
    gmt_create = StrField(field_name="gmtCreate", description="创建时间")
    gmt_modified = StrField(field_name="gmtModified", description="最后修改时间")
    confirm_time = StrField(field_name="confirmTime", description="确认时间")
    last_ship_time = StrField(field_name="lastShipTime", description="承诺发货时间")
    plat_complete_time = StrField(field_name="platCompleteTime", description="平台完成时间")
    complete_time = StrField(field_name="completeTime", description="平台完成时间2")
    signing_time = StrField(field_name="signingTime", description="签收时间")
    trade_time = StrField(field_name="tradeTime", description="下单时间")
    notify_pick_time = StrField(field_name="notifyPickTime", description="通知仓库发货时间")
    is_delete = NumField(field_name="isDelete", description="是否删除")
    company_name_relation = RelationField(Company, field_name="companyName__relation__", follow_with="company_name", query_field="company_name")
    shop_id = StrField(field_name="shopId")
    shop_id_relation = RelationField(Channel, field_name="shopId__relation__", follow_with="shop_id")
    customer_code = StrField(field_name="customerCode", description="客户编码")
    customer_code_relation = RelationField(Customer, field_name="customerCode__relation__", follow_with="customer_code", query_field="customer_code")
    warehouse_id = StrField(field_name="warehouseId", description="仓库id")
    warehouseId_relation = RelationField(Warehouse, field_name="warehouseId__relation__", follow_with="warehouse_id")
    logistic_id = StrField(field_name="logisticId", description="物流公司id")
    logistic_id_relation = RelationField(Logistic, field_name="logisticId__relation__", follow_with="logistic_id")

    register = StrField(field_name="register", description="登记人")
    seller = StrField(field_name="seller", description="业务员")
    auditor = StrField(field_name="auditor", description="审核人")
    reviewer = StrField(field_name="reviewer", description="复核人")
    depart_name = StrField(field_name="departName", description="部门名称")
    customer_name = StrField(field_name="customerName", description="客户名称")
    customer_account = StrField(field_name="customerAccount", description="客户账号")
    shop_code = StrField(field_name="shopCode", description="店铺编码")
    shop_name = StrField(field_name="shopName", description="店铺名称")
    account_name = StrField(field_name="accountName", description="收款账户名称")

    goods_detail_json = StrField(field_name="goodsDetail", description="goodsDetailJson")
    goods_detail_subtable = SubtableField(TradeGoodsDetail, field_name="goodsDetail__relation__", data_source="goods_detail_json", description="订单货品详情")

    paylist_json = StrField(field_name="tradeOrderPayList")
    paylist_subtable = SubtableField(TradePay, field_name="tradeOrderPayList__relation__", data_source="paylist_json", description="订单支付详情")

    class Meta:
        worksheet_id = "trade"

    
class Order(Model):
    order_no = StrField(field_name="orderNo", pk=True, description="发货单号")
    owner_name = StrField(field_name="ownerName", description="货主名称")
    jy_no = StrField(field_name="erporderNo", description="关联销售单号")
    # jy_relation = RelationField(Trade, field_name="erporderNo__relation__", follow_with="jy_no", query_field="jy_no")
    logistic_type = StrField(field_name="logisticTypeName", description="物流公司名称")
    order_status = StrField(field_name="orderStatusName", description="发货单状态名称")
    send_time = StrField(field_name="sendTime", description="发货时间")
    wave_no = StrField(field_name="waveNo", description="波次号")
    estimate_weight = NumField(field_name="estimateWeight", description="发货单预估重量")
    order_fee = NumField(field_name="orderFee", description="操作费用")
    logistic_code = StrField(field_name="logisticCode", description="物流公司编码")
    logistic_relation = RelationField(Logistic, field_name="logisticCode__relation__", follow_with="logistic_code", query_field="logistic_code")
    customer_code = StrField(field_name="customerCode", description="客户编码")
    customer_relation = RelationField(Customer, field_name="customerCode__relation__", follow_with="customer_code", query_field="customer_code")
    shop_id = StrField(field_name="shopId", description="店铺id")
    shop_id_relation = RelationField(Channel, field_name="shopId__relation__", follow_with="shop_id")
    warehouse_id = StrField(field_name="warehouseId", description="仓库id")
    warehouseId_relation = RelationField(Warehouse, field_name="warehouseId__relation__", follow_with="warehouse_id")

    class Meta:
        worksheet_id = "order"