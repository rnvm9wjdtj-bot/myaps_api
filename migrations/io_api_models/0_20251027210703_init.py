from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `t_demand` (
    `MaterialNo` VARCHAR(64) NOT NULL,
    `DemandNo` VARCHAR(64) NOT NULL,
    `ItemNo` VARCHAR(6) NOT NULL,
    `Type` VARCHAR(64),
    `Category` VARCHAR(32) COMMENT 'MTS/MTO',
    `Priority` INT NOT NULL,
    `WorkCenter` VARCHAR(32),
    `Status` VARCHAR(32) COMMENT 'NEW/CRE/REL',
    `Req_Qty` DOUBLE NOT NULL,
    `Create_Date` DATETIME(6),
    `Req_Date` DATETIME(6) NOT NULL,
    `RefNo` VARCHAR(64),
    `PartnerNo` VARCHAR(64),
    `PartnerName` VARCHAR(255),
    `AltGrp` VARCHAR(8) COMMENT '替代组号',
    `Ori_ItemNo` VARCHAR(4),
    `Ori_Qty` DOUBLE,
    `Free1` VARCHAR(255),
    `Free2` VARCHAR(255),
    `Free3` VARCHAR(255),
    `Memo` VARCHAR(255),
    `Sys_Date` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `Sys_User` VARCHAR(32),
    `Sys_Stamp` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_demand_Materia_18edf9` (`MaterialNo`, `DemandNo`, `ItemNo`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_mat_ver` (
    `MaterialNo` VARCHAR(64) NOT NULL,
    `MatVer` VARCHAR(4) NOT NULL,
    `LotFrom` INT,
    `LotTo` INT,
    `Priority` INT,
    `RefNo` VARCHAR(64),
    `Active` VARCHAR(1),
    `Memo` VARCHAR(255),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_mat_ver_Materia_113024` (`MaterialNo`, `MatVer`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_mat_wc` (
    `MaterialNo` VARCHAR(64) NOT NULL,
    `MatVer` VARCHAR(4) NOT NULL,
    `ItemNo` VARCHAR(6) NOT NULL,
    `WorkCenter` VARCHAR(32) NOT NULL COMMENT '工作中心，机台',
    `SortNo` INT NOT NULL COMMENT '唯一',
    `BaseSec` INT NOT NULL,
    `FixQty` INT NOT NULL,
    `FixSec` INT NOT NULL,
    `SF` VARCHAR(1) COMMENT 'S=串行, F=并行',
    `OffSetSec` INT,
    `Memo` VARCHAR(255),
    `Sys_Stamp` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_mat_wc_Materia_e07e78` (`MaterialNo`, `MatVer`, `ItemNo`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_mat_wc_bom` (
    `ProductNo` VARCHAR(64) NOT NULL,
    `MatVer` VARCHAR(4) NOT NULL,
    `ItemNo` VARCHAR(6) NOT NULL,
    `MaterialNo` VARCHAR(64) NOT NULL,
    `Qty` DOUBLE NOT NULL,
    `OffsetHour` INT NOT NULL,
    `TreeNo` INT,
    `MTO` VARCHAR(1) COMMENT 'Y/N',
    `Scrap` DOUBLE COMMENT '%',
    `Alt` VARCHAR(1) COMMENT 'Y/N是否是替代',
    `Memo` VARCHAR(255),
    `Sys_Stamp` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_mat_wc_bo_Product_f06fd1` (`ProductNo`, `MatVer`, `ItemNo`, `MaterialNo`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_mat_wc_mold` (
    `MaterialNo` VARCHAR(64) NOT NULL COMMENT '产品',
    `WorkCenter` VARCHAR(32) NOT NULL COMMENT '机台',
    `MoldNo` VARCHAR(32) NOT NULL,
    `BaseSec` INT COMMENT 'UPH（Units Per Hour）每小时产量',
    `FixSec` INT,
    `Priority` INT,
    `Memo` VARCHAR(255),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_mat_wc_mo_Materia_8b2fee` (`MaterialNo`, `WorkCenter`, `MoldNo`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_material` (
    `MaterialNo` VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '物料',
    `Description` VARCHAR(128) NOT NULL,
    `Size` VARCHAR(128),
    `Plant` VARCHAR(32) NOT NULL COMMENT '工厂',
    `Planner` VARCHAR(64),
    `FIFO` INT NOT NULL COMMENT 'Y-FIFO ,N-最近原则',
    `LeadDay` INT NOT NULL,
    `ExpDay` INT,
    `GRDay` INT NOT NULL,
    `ABC` VARCHAR(8),
    `Unit` VARCHAR(8) COMMENT 'KG/L/g',
    `Price` DECIMAL(10,2),
    `GroupNo` VARCHAR(32),
    `Type` VARCHAR(1),
    `Phantom` VARCHAR(1) COMMENT 'Y/N',
    `PhantomMin` INT NOT NULL COMMENT 'Phantom Offset Time(Minute)',
    `FirmDay` INT,
    `DayGap` INT COMMENT 'MTO Split',
    `CanDelay` VARCHAR(1) COMMENT 'Y/N',
    `LotSize` VARCHAR(2) COMMENT 'EX/FX/D1/D2/D3/D4/D5/D6/W1/W2/W3/W4/M1/M2/VB',
    `LotFix` DOUBLE COMMENT 'Fixed LotSize',
    `LotMin` DOUBLE COMMENT 'Minimum Lot Size',
    `LotMax` DOUBLE COMMENT 'Maximum Lot Size',
    `LotRound` DOUBLE COMMENT 'Rounding value',
    `LotSS` DOUBLE COMMENT 'Safty Stock',
    `LotPoint` DOUBLE COMMENT 'trigger Point',
    `LotTop` DOUBLE COMMENT 'Top Value',
    `PlanItem` VARCHAR(32) COMMENT 'FC PlanItem, PlanGroup',
    `PreDay` INT COMMENT 'FC PreDay',
    `SubDay` INT COMMENT 'FC SubDay',
    `Free1` VARCHAR(255),
    `Free2` VARCHAR(255),
    `Free3` VARCHAR(255),
    `Memo` VARCHAR(255),
    `Sys_User` VARCHAR(32),
    `Sys_Date` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `Sys_Stamp` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_mold` (
    `MoldNo` VARCHAR(32) NOT NULL PRIMARY KEY,
    `MoldName` VARCHAR(255),
    `Type` VARCHAR(8) COMMENT '\'注塑\',\'冲压\',\'压铸\',\'夹具\'',
    `Status` VARCHAR(8) COMMENT '\'空闲\',\'生产中\',\'维修中\',\'报废\'',
    `MoldNum` INT COMMENT '模具穴数',
    `Qty` INT COMMENT '模具台数',
    `Memo` VARCHAR(255)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_supply` (
    `MaterialNo` VARCHAR(64) NOT NULL,
    `SupplyNo` VARCHAR(64) NOT NULL,
    `MatVer` VARCHAR(32),
    `ItemNo` VARCHAR(6) NOT NULL,
    `Type` VARCHAR(64) COMMENT 'PL/MO',
    `Category` VARCHAR(32) COMMENT 'MTO/MTS',
    `Priority` INT NOT NULL,
    `Status` VARCHAR(32) COMMENT 'Release, Confirmation',
    `Avail_Qty` DOUBLE NOT NULL,
    `Create_Date` DATETIME(6),
    `Avail_Date` DATETIME(6) NOT NULL,
    `DT_Req` DATETIME(6),
    `Avail_End_Date` DATETIME(6),
    `BatchNo` VARCHAR(64),
    `VendorNo` VARCHAR(64),
    `PartnerNo` VARCHAR(64),
    `PartnerName` VARCHAR(255),
    `Free1` VARCHAR(255),
    `Free2` VARCHAR(255),
    `Free3` VARCHAR(255),
    `Memo` VARCHAR(255),
    `Sys_Date` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `Sys_User` VARCHAR(32),
    `Sys_Stamp` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `vid` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    UNIQUE KEY `uid_t_supply_Materia_a4804d` (`MaterialNo`, `SupplyNo`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `t_workcenter` (
    `WorkCenter` VARCHAR(32) NOT NULL PRIMARY KEY,
    `WorkCenterName` VARCHAR(255),
    `Pri_WC` INT COMMENT 'Planning时，多个WorkCenter的优先级选定',
    `Bottleneck` VARCHAR(1) COMMENT 'Y/N',
    `SortNo` VARCHAR(4),
    `Plant` VARCHAR(32),
    `Location` VARCHAR(32),
    `Finite` VARCHAR(1) COMMENT 'Y/N',
    `Type` VARCHAR(32),
    `CapNum` INT,
    `CapMax` INT,
    `Worker` DOUBLE COMMENT '工时',
    `SetupNo` VARCHAR(6) COMMENT '切换组',
    `GrpNo` VARCHAR(6) COMMENT '同类',
    `Memo` VARCHAR(255)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "OzQYzAttheMMCRr87s0WN+d+TP/wOfJw9P"
)
