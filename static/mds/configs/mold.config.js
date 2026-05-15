const MDS_PAGE_CONFIG = {
    tableKey: 't_mold',
    tableDisplayName: '模具',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'moldno', title: '模具编号', width: '120px', sortable: true },
            { field: 'moldname', title: '描述', width: '200px' },
            { field: 'type', title: '类型', width: '100px' },
            { field: 'status', title: '状态', width: '100px' },
            { field: 'moldnum', title: '穴数', width: '80px' },
            { field: 'qty', title: '台数', width: '80px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'MoldNo', label: '模具编号' },
                { value: 'MoldName', label: '描述' }
            ],
            numberFields: [
                { value: 'MoldNum', label: '穴数' },
                { value: 'Qty', label: '台数' }
            ],
            enumFields: [
                { value: 'Type', label: '类型', options: [
                    { value: '注塑', label: '注塑' },
                    { value: '冲压', label: '冲压' },
                    { value: '压铸', label: '压铸' },
                    { value: '夹具', label: '夹具' }
                ]},
                { value: 'Status', label: '状态', options: [
                    { value: '空闲', label: '空闲' },
                    { value: '生产中', label: '生产中' },
                    { value: '维修中', label: '维修中' },
                    { value: '报废', label: '报废' }
                ]}
            ]
        }
    }
};
