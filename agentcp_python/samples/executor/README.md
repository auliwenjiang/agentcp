# 代码解释器Agent

这是一个基于ACP协议的代码解释器Agent，可以python的代码执行。

```

# 安装依赖
pip install agentcp RestrictedPython
```

## 使用说明

1. 启动Agent:

```bash
# 创建身份
python create_profile.py

# 修改main.py里的 AGENT_NAME 为你创建的身份信息
python main.py
```

## 功能特性

- ✅ 安全的python代码执行

```python
def add(a, b):
    return a + b
result = add(1, 2)
```

## 调用说明

1. 传入参数 `code` 应为合法的Python代码字符串。
2. 执行代码时，会使用 `RestrictedPython` 进行安全限制，防止执行危险操作。
3. 代码中的 `print` 输出会被 `PrintCollector` 捕获，但当前方法未返回该输出。
4. 最终结果需要存储在名为 `result` 的变量中，方法会尝试从执行环境中获取该变量的值并返回。
5. 代码中可以使用 `import` 进行模块导入，但由于安全性考虑，建议谨慎使用。

## 注意事项

- 复杂代码执行可能失败
- 某些代码可能因为没有模块缺失失败
