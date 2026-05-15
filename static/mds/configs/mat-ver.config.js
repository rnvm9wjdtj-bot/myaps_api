const MDS_PAGE_CONFIG = {
    tableKey: 't_mat_ver',
    tableDisplayName: '产线版本',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'materialno', title: '物料号', width: '120px', sortable: true },
            { field: 'matver', title: '版本号', width: '80px', sortable: true },
            { field: 'description', title: '描述', width: '200px' },
            { field: 'active', title: '激活', width: '80px' },
            { field: 'lotfrom', title: '批量下限', width: '100px' },
            { field: 'lotto', title: '批量上限', width: '100px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'MaterialNo', label: '物料号' },
                { value: 'MatVer', label: '版本号' },
                { value: 'Description', label: '描述' }
            ],
            numberFields: [
                { value: 'LotFrom', label: '批量下限' },
                { value: 'LotTo', label: '批量上限' }
            ],
            enumFields: [
                { value: 'Active', label: '激活', options: [
                    { value: 'Y', label: '是' },
                    { value: 'N', label: '否' }
                ]}
            ]
        }
    }
};
