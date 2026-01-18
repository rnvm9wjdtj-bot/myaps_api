from apps.data_opt.components._base import BaseConnection

# 测试数据
test_data = {'a': 1, 'b': 2, 'c': [{'d': 4}, {'e': 5}]}

# 调用函数展开'c'列表
result = BaseConnection.datapro_expand_parent_child_data(test_data, 'c')

# 打印结果
print("测试数据:", test_data)
print("展开'c'列表后的结果:", result)

# 验证结果是否符合预期
expected = [{'a': 1, 'b': 2, 'c/d': 4}, {'a': 1, 'b': 2, 'c/e': 5}]
print("预期结果:", expected)
print("测试通过:", result == expected)