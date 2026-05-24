"""RAG知识库重构：从面试导向→觉醒导向
保留非面试内容 + 思维框架 + 新增3个品类
"""
import json, re, sys

with open('seed.py', 'r') as f:
    content = f.read()

# 提取 SEED_DOCUMENTS 数组
match = re.search(r'SEED_DOCUMENTS\s*=\s*\[(.*?)\]', content, re.DOTALL)
if not match:
    print("ERROR: couldn't find SEED_DOCUMENTS")
    sys.exit(1)

docs_text = match.group(1)

# 解析每个文档块
docs = []
current = {}
in_doc = False
brace_depth = 0
buffer = ""

for line in content.split('\n'):
    if 'SEED_DOCUMENTS = [' in line:
        continue
    if line.strip().startswith(']') and not in_doc:
        break
    buffer += line + '\n'

# 用更简单的方法：按 "metadata" 行解析
parts = re.split(r'\n    \},\n', content.split('SEED_DOCUMENTS = [\n')[1].split('\n]')[0])
print(f"Found {len(parts)} document blocks")

# 统计 type 分布
types = {}
for part in parts:
    m = re.search(r'"type":\s*"(\w+)"', part)
    if m:
        t = m.group(1)
        types[t] = types.get(t, 0) + 1

print("Current type distribution:")
for t, c in sorted(types.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# 保留的 type
KEEP_TYPES = {
    'universal_ai', 'psychology', 'social_knowledge', 'reality_check',
    'ai_era', 'future_guide',
}
# 框架类（保留去PM化）
FRAMEWORK_KEEP = {
    'STAR法则', 'MECE原则', 'KANO模型', '金字塔原理', '第一性原理',
    'SWOT分析', 'PEST分析', 'MVP原则', '成长型思维', 'AARRR模型',
    '需求优先级排序',
}

keep_count = 0
remove_count = 0
framework_count = 0

for part in parts:
    m_type = re.search(r'"type":\s*"(\w+)"', part)
    m_source = re.search(r'"source":\s*"([^"]+)"', part)
    if not m_type:
        continue
    t = m_type.group(1)
    src = m_source.group(1) if m_source else ''
    
    if t in KEEP_TYPES:
        keep_count += 1
    elif t == 'framework' and any(fw in src for fw in FRAMEWORK_KEEP):
        framework_count += 1
    else:
        remove_count += 1

print(f"\nPlan: keep {keep_count} (non-interview), keep {framework_count} (frameworks), remove {remove_count}")
print(f"After removal: {keep_count + framework_count} documents remain")
print(f"Need to add: {115 - keep_count - framework_count} new documents (target 115)")
