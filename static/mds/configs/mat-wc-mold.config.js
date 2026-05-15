const MDS_PAGE_CONFIG = {
    tableKey: 't_mat_wc_mold',
    tableDisplayName: '机台模具',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'materialno', title: '物料号', width: '120px', sortable: true },
            { field: 'workcenter', title: '工作中心', width: '100px' },
            { field: 'itemno', title: '工序号', width: '80px' },
            { field: 'moldno', title: '模具编号', width: '120px' },
            { field: 'basesec', title: 'UPH', width: '100px' },
            { field: 'priority', title: '优先级', width: '80px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'MaterialNo', label: '物料号' },
                { value: 'WorkCenter', label: '工作中心' },
                { value: 'ItemNo', label: '工序号' },
                { value: 'MoldNo', label: '模具编号' }
            ],
            numberFields: [
                { value: 'BaseSec', label: 'UPH' },
                { value: 'Priority', label: '优先级' }
            ],
            enumFields: []
        }
    }
};
