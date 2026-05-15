const MDS_PAGE_CONFIG = {
    tableKey: 't_workcenter',
    tableDisplayName: '工作中心',

    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'workcenter', title: '工作中心', width: '120px', sortable: true },
            { field: 'description', title: '描述', width: '200px' },
            { field: 'bottleneck', title: '瓶颈', width: '80px' },
            { field: 'finite', title: '有限产能', width: '100px' },
            { field: 'capacity', title: '产能', width: '100px' },
            { field: '_source_system', title: '来源', width: '80px' }
        ],

        defaultSortField: '_createtime',
        defaultSortDir: 'desc',

        advancedFilterCategories: {
            stringFields: [
                { value: 'WorkCenter', label: '工作中心' },
                { value: 'Description', label: '描述' }
            ],
            numberFields: [
                { value: 'Capacity', label: '产能' }
            ],
            enumFields: [
                { value: 'Bottleneck', label: '瓶颈', options: [
                    { value: 'Y', label: '是' },
                    { value: 'N', label: '否' }
                ]},
                { value: 'Finite', label: '有限产能', options: [
                    { value: 'Y', label: '是' },
                    { value: 'N', label: '否' }
                ]}
            ]
        }
    }
};
