# coding: utf-8

import json
import hashlib
import requests
from urllib.parse import quote
import os
from typing import Dict, Any, Optional, OrderedDict
from datetime import datetime, timedelta


from ._base import (
    console_log,
    DataProcessor, globalconst, CACHE_JSON,
    BaseConnection, convert_timeunit, clean_value, #reset_default_values,
    BaseModel as PydanticModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold
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

            "hap_worksheet": "company",
            "conflict_fields": ("companyCode", ),
            "data_node": None
        },

        "全部仓库": {
            "method": "erp.warehouse.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "hap_worksheet": "warehouse",
            "conflict_fields": ("warehouseId", ),
            "data_node": "warehouseInfo"
        },

        "全部部门": {
            "method": "erp.depart.query",
            "biz_content": {},
            "hap_worksheet": "depart",
            "conflict_fields": ("departCode", ),
            "data_node": None
        },

        "全部员工": {
            "method": "erp.user.search",
            "biz_content": {
                "cols": "companyId,companyName,email,mainDepartId,mainDepartName,mobile,realName,userId,userName",
                "pageIndex": None,
                "pageSize": None
            },
            "hap_worksheet": "staff",
            "conflict_fields": ("userName", ),
            "data_node": None
        },

        "全部销售渠道": {
            "method": "erp.sales.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "hap_worksheet": "channel",
            "conflict_fields": ("channelCode", ),
            "data_node": "salesChannelInfo"
        },

        "货品全量分类": {
            "method": "erp.goodscate.get",
            "biz_content": {},
            "hap_worksheet": "goodscate",
            "conflict_fields": ("cateCode", ),
            "data_node": None
        },

        "全量物流公司": {
            "method": "erp.logistic.get",
            "biz_content": {"pageIndex": None, "pageSize": None},
            "hap_worksheet": "logistic",
            "conflict_fields": ("id", ),
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
            "hap_worksheet": "bankaccounts",
            "conflict_fields": ("accId", ),
            "data_node": None
        },

        # "新增SKU": {
        #     "method": "erp.storage.goodslist",
        #     "biz_content": "{{'startDate': '{start}', 'endDate': '{end}', 'pageSize': {page_size}, 'pageIndex': {page_index}, 'isQueryDelete': 0, 'skuIsBlockup': 0, 'isBlockup': 0, 'isPackageGood': 0}}",
        #     "hap_worksheet": "sku",
        #     "conflict_fields": None,
        #     "data_node": "goods"
        # },
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
            "hap_worksheet": "sku",
            "conflict_fields": ("skuId", ),
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
            "hap_worksheet": "customer",
            "conflict_fields": ("customerId", ),
            "data_node": None
        },

        "更新JY单": {
            "method": "erp.storage.goodslist",
            "biz_content": "{{'startModified': '{start}', 'endModified': '{end}', 'pageSize': {page_size}, 'pageIndex': {page_index}, 'hasTotal': 1, 'fields': 'totalResults,trades,checkTotal,tradeNo,otherFee,chargeCurrency,accountName,payType,payNo,sellerMemo,buyerMemo,goodsDetail,goodsDetail.goodsNo,goodsDetail.goodsName,goodsDetail.specName,goodsDetail.barcode,goodsDetail.sellCount,goodsDetail.unit,goodsDetail.sellPrice,goodsDetail.sellTotal,goodsDetail.cost,goodsDetail.discountTotal,goodsDetail.discountPoint,goodsDetail.taxFee,goodsDetail.shareFavourableFee,goodsDetail.estimateWeight,goodsDetail.goodsMemo,goodsDetail.cateName,goodsDetail.brandName,goodsDetail.goodsTags,goodsDetail.isFit,goodsDetail.isGift,goodsDetail.discountFee,goodsDetail.taxRate,goodsDetail.estimateGoodsVolume,goodsDetail.isPresell,goodsDetail.customerPrice,goodsDetail.customerTotal,goodsDetail.tradeGoodsNo,goodsDetail.tradeGoodsName,goodsDetail.tradeGoodsSpec,goodsDetail.tradeGoodsUnit,goodsDetail.sourceSubtradeNo,goodsDetail.platCode,goodsDetail.platGoodsId,goodsDetail.subTradeId,goodsDetail.goodsDelivery,goodsDelivery.sendCount,goodsDelivery.productionDate,goodsDelivery.expirationDate,goodsDelivery.batchNo,goodsDelivery.expireDate,goodsDelivery.productDate,goodsDetail.platAuthorId,goodsDetail.platAuthorName,goodsDetail.isPlatGift,goodsDetail.goodsPlatDiscountFee,goodsDetail.tradeOrderGoodsDiscountInfoDtoList,tradeOrderGoodsDiscountInfoDtoList.discountFee,tradeOrderGoodsDiscountInfoDtoList.discountName,goodsDetail.shareFavourableAfterFee,goodsDetail.divideSellTotal,goodsDetail.shareOrderDiscountFee,goodsDetail.shareOrderPlatDiscountFee,goodsDetail.sourceTradeNo,goodsDetail.actualSendCount,goodsDetail.platSkuId,goodsDetail.customerTradeNo,goodsDetail.customerSubtradeNo,goodsDetail.PlatCustomData,goodsDetail.assessmentCostLocal,goodsDetail.assessmentGrossProfitLocal,goodsDetail.assessmentGrossProfitPercent,goodsDetail.goodsCompassSourceContentType,goodsDetail.goodsSeller,goodsDetail.inventoryWarehouseId,goodsDetail.inventoryWarehouseName,goodsDetail.specId,goodsDetail.goodsId,goodsDetail.outerId,goodsDetail.apiType,goodsDetail.tradeId,goodsDetail.skuImgUrl,goodsDetail.needProcessCount,goodsDetail.goodsFlagIds,goodsDetail.goodsFlagNames,appendMemo,tradeFrom,register,seller,auditor,reviewer,estimateWeight,packageWeight,tradeCount,goodsTypeCount,freezeReason,abnormalDescription,onlineTradeNo,goodslist,gmtCreate,gmtModified,stockoutNo,confirmTime,departName,lastShipTime,payStatus,chargeCurrencyCode,chargeExchangeRate,tradeStatus,grossProfit,estimateVolume,customerTypeName,customerGradeName,customerTags,customerCode,customerDiscount,specialReminding,blackList,tradeTime,country,state,city,district,town,zip,payTime,countryCode,cityCode,invoiceType,payerName,payerRegno,payerBankAccount,payerPhone,auditTime,payerAddress,invoiceNo,invoiceCode,invoiceStatus,payerBankName,preTypedetail,firstPayment,finalPayment,firstPaytime,finalPaytime,reviewTime,activationTime,customerTotalFee,customerDiscountFee,notifyPickTime,consignTime,orderNo,customerPostFee,shopId,shopName,tradeOrderPayList,customerPayment,companyName,tradeOrderColumnExt,isBillCheck,warehouseCode,warehouseName,logisticName,tradeId,billDate,logisticType,mainPostid,tradeType,totalFee,taxFee,receivedPostFee,discountFee,payment,couponFee,receivedTotal,postFee,isTableSwitch,completeTime,shopcode,signingTime,goodsSerial,otherPaymentFees,tradeOrderGoodsColumnExts,isDelete,localPayment,localExchangeRate,customerAccount,localCurrencyCode,platCompleteTime,buyerOpenUid,tradeOrderAssemblyGoodsDtoList,tradeOrderRefundTime,assemblyGoodsDetail,apiType,logisticCode,agentShopName,tradeStatusExplain,flagIds,flagNames,sysFlagIds,shopTypeCode,sourceAfterNo,ticketCodeList,allCompassSourceContentType,customerName,invoiceAmount,realFee,packageDetail.state,finReceiptTime,extraLogisticNo,warehouseId,id,govSubsidy,pickUpTime,tradeOrderPre,scrollId,chargeType,chargeCurrency,chargeAccount,accountName,payType,payNo,payment,chargeCurrencyCode,chargeExchangeRate,columnExt.tradeId,goodsSerial.subTradeId,goodsSerial.skuId,goodsSerial.serialNo,goodsSerial.serialNo2,expense.expenseFee,expense.expenseItemName,subTradeId,tradeId,tradeOrderAssemblyGoodsDtoList.goodsNo,tradeOrderAssemblyGoodsDtoList.unit,tradeOrderAssemblyGoodsDtoList.specId,tradeOrderAssemblyGoodsDtoList.goodsId,tradeOrderAssemblyGoodsDtoList.tradeId,tradeOrderAssemblyGoodsDtoList.specName,tradeOrderAssemblyGoodsDtoList.goodsName,tradeOrderAssemblyGoodsDtoList.sellCount,tradeOrderAssemblyGoodsDtoList.subTradeId,tradeOrderAssemblyGoodsDtoList.baseUnitSellCount,tradeOrderAssemblyGoodsDtoList.assemblyGoodsDelivery,tradeId,specId,batchNo,expireDate,subTradeId,productDate,packageDetail.state,packageDetail.city,packageDetail.town,packageDetail.district,packageDetail.isGift,packageDetail.barcode,packageDetail.tradeNo,packageDetail.buyerMemo,packageDetail.sellCount,packageDetail.isPlatGift,packageDetail.logisticNo,packageDetail.sellerMemo,packageDetail.consignTime,packageDetail.logisticCode,packageDetail.logisticName,packageDetail.sourceTradeNo,packageDetail.warehouseName,packageDetail.sourceSubtradeNo,frstPaytime,firstPayment,finalPaytime,finalPayment,preTypedetail,sourceTradeNo'}}",
            "hap_worksheet": "trade",
            "conflict_fields": ("tradeId", ),
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
            "hap_worksheet": "businessOrder",
            "conflict_fields": ("tradeNo", ),
            "data_node": None
        },

        "发货单": {
            "method": "wms.order.query-info.page",
            "biz_content": {
                "startFinishTime": None,
                "endFinishTime": None,
                "pageSize": None,
                "pageIndex": None,
                "hasTotal": 1
            },
            "hap_worksheet": "order",
            "conflict_fields": None,
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


    def call_api(self, base_url, biz_content, method, version) -> Dict[str, Any]:

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

        response = self._session.post(url=url, json=payload, headers=headers)

        response_json = response.json()
        return response_json


    def pull_from_source(self, source_name: str, biz_content_format: Optional[Dict[str, Any]]=None):
        source = self.config.PULL_SOURCE[source_name]
        method = source["method"]
        field_map = source.get("field_map", {})
        biz_content = source["biz_content"]
        if biz_content_format:
            biz_content.update(biz_content_format)
        version = source.get("version", "v1.0")
        data_node = source["data_node"]
        # conflict_fields = source["conflict_fields"]
        # hap_worksheetid = source["hap_worksheet"]

        page_size = 200
        page_index = 0

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
                result_data = result_data[data_node]
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
            yield data_list
            if len(result_data) < page_size or (not "pageSize" in biz_content and page_index > 0):
                break


    def push_into_target(self, *args, **kwargs):
        return super().push_to_target(*args, **kwargs)