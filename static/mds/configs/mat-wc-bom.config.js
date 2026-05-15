const MDS_PAGE_CONFIG = {
    tableKey: 't_mat_wc_bom',
    tableDisplayName: 'BOM',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'productno', title: '父件料号', width: '120px', sortable: true },
            { field: 'matver', title: '版本号', width: '80px' },
            { field: 'itemno', title: '工序号', width: '80px' },
            { field: 'materialno', title: '子件料号', width: '120px' },
            { field: 'qty', title: '用量', width: '100px' },
            { field: 'scrap', title: '损耗率', width: '80px' },
            { field: 'mto', title: 'MTO', width: '80px' },
            { field: 'alt', title: '替代料', width: '80px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'ProductNo', label: '父件料号' },
                { value: 'MatVer', label: '版本号' },
                { value: 'ItemNo', label: '工序号' },
                { value: 'MaterialNo', label: '子件料号' }
            ],
            numberFields: [
                { value: 'Qty', label: '用量' },
                { value: 'Scrap', label: '损耗率' }
            ],
            enumFields: [
                { value: 'MTO', label: 'MTO', options: [
                    { value: 'Y', label: '是' },
                    { value: 'N', label: '否' }
                ]},
                { value: 'Alt', label: '替代料', options: [
                    { value: 'Y', label: '是' },
                    { value: 'N', label: '否' }
                ]}
            ]
        }
    }
};
