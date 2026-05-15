const MDS_PAGE_CONFIG = {
    tableKey: 't_mat_wc',
    tableDisplayName: '工艺路线',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'materialno', title: '物料号', width: '120px', sortable: true },
            { field: 'matver', title: '版本号', width: '80px' },
            { field: 'itemno', title: '工序号', width: '80px' },
            { field: 'workcenter', title: '工作中心', width: '100px' },
            { field: 'sf', title: '串并行', width: '80px' },
            { field: 'basesec', title: '基础工时', width: '100px' },
            { field: 'sortno', title: '排序', width: '80px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'MaterialNo', label: '物料号' },
                { value: 'MatVer', label: '版本号' },
                { value: 'ItemNo', label: '工序号' },
                { value: 'WorkCenter', label: '工作中心' }
            ],
            numberFields: [
                { value: 'BaseSec', label: '基础工时' },
                { value: 'SortNo', label: '排序' }
            ],
            enumFields: [
                { value: 'SF', label: '串并行', options: [
                    { value: 'S', label: '串行' },
                    { value: 'P', label: '并行' }
                ]}
            ]
        }
    }
};
