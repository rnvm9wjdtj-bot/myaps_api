const MDS_PAGE_CONFIG = {
    tableKey: 't_material',
    tableDisplayName: '物料',
    
    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'materialno', title: '物料号', width: '100px', sortable: true },
            { field: 'description', title: '物料描述', width: '150px' },
            { field: 'size', title: '规格' },
            { field: 'plant', title: '工厂', width: '70px' },
            { field: 'planner', title: '计划员' },
            { field: 'fifo', title: 'FIFO', width: '50px' },
            { field: 'leadday', title: '提前期', width: '60px' },
            { field: 'expday', title: '保质期', width: '60px' },
            { field: 'grday', title: '质检期', width: '60px' },
            { field: 'abc', title: 'ABC', width: '50px' },
            { field: 'unit', title: '单位', width: '50px' },
            { field: 'price', title: '价格', width: '80px' },
            { field: 'groupno', title: '型号' },
            { field: 'type', title: '类型', width: '50px' },
            { field: 'phantom', title: '虚拟件', width: '60px' },
            { field: 'phantommin', title: '虚拟时间', width: '70px' },
            { field: 'firmday', title: '固定天数', width: '60px' },
            { field: 'daygap', title: '拆分天数', width: '60px' },
            { field: 'candelay', title: '可延迟', width: '60px' },
            { field: 'lotsize', title: '批量策略', width: '70px' },
            { field: 'lotfix', title: '固定批', width: '60px' },
            { field: 'lotmin', title: '最小批', width: '60px' },
            { field: 'lotmax', title: '最大批', width: '60px' },
            { field: 'lotround', title: '取整值', width: '60px' },
            { field: 'lotss', title: '安全库存', width: '60px' },
            { field: 'lotpoint', title: '订货点', width: '60px' },
            { field: 'lottop', title: '最大库存', width: '60px' },
            { field: 'planitem', title: '产品组' },
            { field: 'preday', title: '向前冲销', width: '60px' },
            { field: 'subday', title: '向后冲销', width: '60px' },
            { field: 'free1', title: '自定义1' },
            { field: 'free2', title: '自定义2' },
            { field: 'free3', title: '自定义3' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],
        
        defaultSortField: '_createtime',
        defaultSortDir: 'desc',
        
        advancedFilterCategories: {
            stringFields: [
                { value: 'MaterialNo', label: '物料号' },
                { value: 'Description', label: '物料描述' },
                { value: 'Plant', label: '工厂' },
                { value: 'Planner', label: '计划员' },
                { value: 'Unit', label: '单位' }
            ],
            numberFields: [
                { value: 'LeadDay', label: '提前期' },
                { value: 'ExpDay', label: '保质期' },
                { value: 'GRDay', label: '质检期' },
                { value: 'Price', label: '价格' },
                { value: 'PhantomMin', label: '虚拟时间' },
                { value: 'FirmDay', label: '固定天' },
                { value: 'DayGap', label: '拆分天' },
                { value: 'LotFix', label: '固定批' },
                { value: 'LotMin', label: '最小批' },
                { value: 'LotMax', label: '最大批' }
            ],
            enumFields: [
                { value: 'ABC', label: 'ABC分类', options: [
                    { value: 'A', label: 'A类' },
                    { value: 'B', label: 'B类' },
                    { value: 'C', label: 'C类' }
                ]},
                { value: 'Type', label: '类型', options: [
                    { value: 'E', label: '自制件(E)' },
                    { value: 'F', label: '采购件(F)' }
                ]},
                { value: 'Phantom', label: '虚拟件', options: [
                    { value: 'Y', label: '是(Y)' },
                    { value: 'N', label: '否(N)' }
                ]},
                { value: 'CanDelay', label: '可延迟', options: [
                    { value: 'Y', label: '是(Y)' },
                    { value: 'N', label: '否(N)' }
                ]},
                { value: 'LotSize', label: '批量策略', options: [
                    { value: 'EX', label: '一对一(EX)' },
                    { value: 'FX', label: '固定批(FX)' },
                    { value: 'VB', label: '重订货点(VB)' },
                    { value: 'D1', label: '按1天合并(D1)' },
                    { value: 'D2', label: '按2天合并(D2)' },
                    { value: 'D3', label: '按3天合并(D3)' },
                    { value: 'D4', label: '按4天合并(D4)' },
                    { value: 'D5', label: '按5天合并(D5)' },
                    { value: 'D6', label: '按6天合并(D6)' },
                    { value: 'W1', label: '按1周合并(W1)' },
                    { value: 'W2', label: '按2周合并(W2)' },
                    { value: 'W3', label: '按3周合并(W3)' },
                    { value: 'W4', label: '按4周合并(W4)' },
                    { value: 'M1', label: '按1月合并(M1)' },
                    { value: 'M2', label: '按2月合并(M2)' },
                    { value: 'M3', label: '按3月合并(M3)' }
                ]},
                { value: 'FIFO', label: 'FIFO', options: [
                    { value: '0', label: '最近原则' },
                    { value: '1', label: 'FIFO' }
                ]}
            ]
        }
    }
};
