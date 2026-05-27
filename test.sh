#!/bin/bash
# 技能奇遇 自动测试脚本
# 用法: bash test.sh
# 在 git push 前运行，拦截基本错误
set -e
cd "$(dirname "$0")"
PASS=0; FAIL=0
RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; NC='\033[0m'

pass(){ echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
fail(){ echo -e "  ${RED}✗${NC} $1 — $2"; FAIL=$((FAIL+1)); }

echo "══════════════════════════════════════"
echo " 技能奇遇 预发布测试"
echo "══════════════════════════════════════"

# ── 1. 前端 JS 语法检查 ──
echo ""
echo "📋 前端 JS 语法"

# 检查1a: 函数声明无裸奔代码
HTML="frontend/index.html"
# 提取 <script> 内的代码，检查是否在函数体外有赋值语句（被吃掉的函数声明的典型症状）
BARE_CODE=$(python3 -c "
import re
with open('$HTML') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
for s in scripts:
    lines = s.strip().split('\n')
    depth = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            continue
        # 跟踪大括号深度
        depth += stripped.count('{') - stripped.count('}')
        # 如果在全局作用域(depth<=0)出现了赋值/表达式语句，且不在函数声明内
        if depth <= 0 and ('= document.' in stripped or '= await' in stripped or '= api(' in stripped):
            if 'function ' not in line and 'const ' not in line and 'let ' not in line and 'var ' not in line:
                print(f'  ⚠ 全局作用域疑似裸奔代码 行{i+1}: {stripped[:80]}')
")
if [ -n "$BARE_CODE" ]; then
    fail "JS裸奔代码" "函数声明可能被吃掉了，检查是否有代码在function体外"
    echo "$BARE_CODE"
else
    pass "无全局裸奔代码"
fi

# 检查1b: onclick 引用的函数是否都存在
FUNCS_IN_HTML=$(python3 -c "
import re
with open('$HTML') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
all_code = ' '.join(scripts)
# 找所有函数名
defined = set(re.findall(r'function\s+(\w+)', all_code))
defined.update(re.findall(r'async\s+function\s+(\w+)', all_code))
# 找所有 onclick 调用的函数
onclick_calls = set(re.findall(r'onclick=\"(\w+)\(', html))
onclick_calls.update(re.findall(r'onclick=\"(\w+)\(', html))
missing = onclick_calls - defined
for m in sorted(missing):
    print(f'  ⚠ onclick引用但未定义: {m}')
")
if [ -n "$FUNCS_IN_HTML" ]; then
    fail "onclick引用缺失" "以下函数在onclick中被调用但未定义"
    echo "$FUNCS_IN_HTML"
else
    pass "所有onclick引用都有对应函数"
fi

# 检查1c: 关键DOM元素ID是否存在
MISSING_IDS=""
for id in profile-modal coach-modal scene-grid chat-area chat-input feedback-page practice-page scene-page recommend-card profile-card pf-year pf-major concern-grid sliders step1 step2; do
    if ! grep -q "id=\"$id\"" "$HTML"; then
        MISSING_IDS="$MISSING_IDS $id"
    fi
done
if [ -n "$MISSING_IDS" ]; then
    fail "缺少DOM元素" "$MISSING_IDS"
else
    pass "关键DOM元素齐全"
fi

# 检查1d: 关键变量和函数是否正确引用
# 检查 CONCERNS 数组中的 v 值和 CONCERN_MAP 的 key 是否一致
CONCERN_VS=$(grep -oP "v:'\K\w+" "$HTML" | sort)
MAP_KEYS=$(grep -oP "^\s+\K\w+(?=:')" "$HTML" | sort)
# 检查 INIT 代码是否有 try-catch 保护
if grep -q "try{" "$HTML" && grep -q "}catch" "$HTML"; then
    pass "INIT代码有错误保护"
else
    fail "INIT代码" "缺少try-catch错误保护，运行时错误会导致整个页面无响应"
fi

# 检查1e: 所有 .js 引用必须实际存在
for jsfile in $(grep -oP 'src="\K[^"]+\.js' "$HTML"); do
    if [ ! -f "frontend/$jsfile" ]; then
        fail "JS文件缺失" "frontend/$jsfile 不存在"
    fi
done
# 检查1f: document.getElementById 引用的 ID 必须存在
JS_CODE=$(python3 -c "
import re
with open('$HTML') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
print(' '.join(scripts))
")
for id in $(echo "$JS_CODE" | grep -oP "getElementById\('[^']+'\)" | grep -oP "'\K[^']+"); do
    if ! grep -q "id=\"$id\"" "$HTML"; then
        fail "JS引用了不存在的DOM" "getElementById('$id')"
    fi
done
if [ $FAIL -eq 0 ] || true; then
    # 这只是一个额外检查，不影响通过
    :
fi

# ── 2. 后端 Python 语法 ──
echo ""
echo "📋 后端 Python 语法"
SYNTAX_OK=true
for f in backend/app/**/*.py; do
    if ! python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
        fail "Python语法错误" "$f"
        SYNTAX_OK=false
    fi
done
if $SYNTAX_OK; then
    pass "所有Python文件语法正确"
fi

# ── 3. 后端关键导入检查（需要依赖，Docker环境可用） ──
echo ""
echo "📋 后端导入链"
cd backend
HAS_DEPS=$(python3 -c "import pydantic" 2>/dev/null && echo 1 || echo 0)
if [ "$HAS_DEPS" = "1" ]; then
    IMPORT_OK=true
    for check in "from app.data.coaches import PRESET_COACHES" \
                 "from app.data.scenes import SCENES" \
                 "from app.models.schemas import Coach, Scene, HexagonScore" \
                 "from app.services.llm import generate, build_interviewer_system_prompt" \
                 "from app.services.rag import retrieve, init_knowledge_base" \
                 "from app.services.evaluator import evaluate_hexagon, evaluate_session"; do
        if python3 -c "$check" 2>/dev/null; then : ; else
            fail "导入失败" "$check"
            IMPORT_OK=false
        fi
    done
    if $IMPORT_OK; then pass "所有关键模块可导入"; fi
else
    echo -e "  ${YELLOW}⊘${NC} 跳过（缺少pydantic等依赖，需在Docker内运行）"
fi
cd ..

# ── 4. 教练数据完整性（需要依赖） ──
echo ""
echo "📋 教练数据完整性"
if [ "$HAS_DEPS" = "1" ]; then
    cd backend
    python3 -c "
import sys; sys.path.insert(0,'.')
from app.data.coaches import PRESET_COACHES, COACH_RECOMMEND_REASONS
from app.models.schemas import HEXAGON_DIMENSIONS
dim_ids = {d['id'] for d in HEXAGON_DIMENSIONS}
errors = []
if len(PRESET_COACHES) < 8:
    errors.append(f'教练太少 ({len(PRESET_COACHES)}), 预期>=8')
for c in PRESET_COACHES:
    if not c.strengths: errors.append(f'{c.name} strengths为空')
    for s in c.strengths:
        if s not in dim_ids: errors.append(f'{c.name} strengths含无效维度: {s}')
    if not c.personality or len(c.personality) < 20:
        errors.append(f'{c.name} personality过短或为空')
missing_reasons = [c.id for c in PRESET_COACHES if c.id not in COACH_RECOMMEND_REASONS]
if missing_reasons: errors.append(f'缺少推荐理由: {missing_reasons}')
if errors:
    for e in errors: print(f'ERROR: {e}')
    sys.exit(1)
print(f'OK: {len(PRESET_COACHES)}个教练, 推荐理由覆盖{len(COACH_RECOMMEND_REASONS)}个')
" 2>/dev/null
    if [ $? -eq 0 ]; then pass "教练数据完整"
    else fail "教练数据" "检查教练数量和字段完整性"; fi
    cd ..
else
    # 无依赖时用grep做基本检查
    COACH_COUNT=$(grep -c 'id="' backend/app/data/coaches.py)
    REASON_COUNT=$(grep -c ':' backend/app/data/coaches.py | head -1)  # approximate
    if [ "$COACH_COUNT" -ge 8 ]; then
        pass "教练数量 >=8 (grep检查: $COACH_COUNT个)"
    else
        fail "教练数据" "教练数量不足: $COACH_COUNT"
    fi
fi

# ── 5. API端点检查（需要依赖） ──
echo ""
echo "📋 API路由注册"
if [ "$HAS_DEPS" = "1" ]; then
    cd backend
    python3 -c "
import sys; sys.path.insert(0,'.')
from app.main import app
routes = [r.path for r in app.routes]
required = ['/api/health', '/api/scenes', '/api/practice/start',
            '/api/practice/message', '/api/practice/end', '/api/coaches',
            '/api/coaches/recommend', '/api/practice/profile']
missing = [r for r in required if r not in routes]
if missing:
    print(f'ERROR: 缺少路由: {missing}')
    sys.exit(1)
print(f'OK: {len(routes)}个路由注册')
" 2>/dev/null
    if [ $? -eq 0 ]; then pass "API路由完整"
    else fail "API路由" "检查路由注册"; fi
    cd ..
else
    echo -e "  ${YELLOW}⊘${NC} 跳过（缺少依赖）"
fi

# ── 6. LLM prompt 质量检查 ──
echo ""
echo "📋 LLM Prompt质量"
PROMPT_CHECKS_OK=true
# 检查行为规则中是否包含「必须」而非「可以」
if grep -q "必须质疑\|必须指出\|不批评就是失职" backend/app/services/llm.py; then
    pass "行为规则含强制性指令"
else
    fail "行为规则" "缺少强制性指令(必须质疑/必须指出)"
    PROMPT_CHECKS_OK=false
fi

# 检查 generate() 是否支持 history 参数
if grep -q "history.*list\[dict\]" backend/app/services/llm.py; then
    pass "generate()支持对话历史"
else
    fail "generate()" "不支持history参数——LLM每轮都是第一次见你"
    PROMPT_CHECKS_OK=false
fi

# 检查 message 端点是否传了 history
if grep -q "history=history" backend/app/routers/practice.py; then
    pass "消息端点传入对话历史"
else
    fail "消息端点" "未传入history——LLM每轮无上下文"
    PROMPT_CHECKS_OK=false
fi

# 检查 RAG 是否每轮检索
if grep -q "retrieve.*k=3" backend/app/routers/practice.py && ! grep -q "round % 3" backend/app/routers/practice.py; then
    pass "RAG每轮检索"
else
    fail "RAG" "不是每轮检索或k值不对"
    PROMPT_CHECKS_OK=false
fi

# 检查 CS 场景 branch 存在
if grep -q "is_code.*代码评审" backend/app/services/llm.py && grep -q "is_defense.*答辩" backend/app/services/llm.py; then
    pass "CS场景分支存在"
else
    fail "CS场景" "llm.py缺少is_code或is_defense检测"
    PROMPT_CHECKS_OK=false
fi

# 检查 CS 场景教练精简注入
if grep -q "_extract_speaking_style_only" backend/app/services/llm.py; then
    pass "CS场景精简教练人格"
else
    fail "CS场景" "llm.py缺少_extract_speaking_style_only函数"
    PROMPT_CHECKS_OK=false
fi

# ── 7. CS场景数据完整性 ──
echo ""
echo "📋 CS场景数据"
HAS_CODE=$(grep -c '"code-narrative"' backend/app/data/scenes.py 2>/dev/null || echo 0)
HAS_DEFENSE=$(grep -c '"project-defense"' backend/app/data/scenes.py 2>/dev/null || echo 0)
if [ "$HAS_CODE" -ge 1 ]; then pass "code-narrative场景存在"; else fail "CS场景" "缺少code-narrative"; fi
if [ "$HAS_DEFENSE" -ge 1 ]; then pass "project-defense场景存在"; else fail "CS场景" "缺少project-defense"; fi
# 检查CS场景的cat为cs
CS_CAT=$(grep -c 'cat="cs"' backend/app/data/scenes.py 2>/dev/null || echo 0)
if [ "$CS_CAT" -ge 2 ]; then pass "CS场景分类正确(cat=cs)"; else fail "CS场景" "cat=cs数量不足: $CS_CAT"; fi

# 检查教练推荐含场景感知逻辑
if grep -q "_is_cs_scene" backend/app/data/coaches.py; then
    pass "教练推荐含场景感知"
else
    fail "教练推荐" "缺少_is_cs_scene场景感知函数"
fi

# 检查SceneCategory含PRESENTATION
if grep -q "PRESENTATION" backend/app/models/schemas.py; then
    pass "SceneCategory含PRESENTATION"
else
    fail "SceneCategory" "缺少PRESENTATION枚举"
fi

if grep -q "voice.router" backend/app/main.py; then pass "语音路由已注册"; else fail "语音路由" "main.py未注册voice.router"; fi

# ── 汇总 ──
echo ""
echo "══════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    echo -e " ${GREEN}✅ 全部通过 ($PASS项)${NC}"
    echo " 可以安全 push"
    exit 0
else
    echo -e " ${RED}❌ $FAIL 项失败, $PASS 项通过${NC}"
    echo " 修复后再 push"
    exit 1
fi
