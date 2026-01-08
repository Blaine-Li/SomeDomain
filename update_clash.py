import requests
import yaml
import os

# ================= 配置区域 =================

FILES_TO_PROCESS = [
    'clashstga.yaml', 
]

# GitHub Proxy (可选)
URL_PREFIX = "" 

# ================= 核心常量定义 =================

# 仅允许的规则类型（全部大写，用于忽略大小写匹配）
VALID_RULE_TYPES = {
    'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'DOMAIN-WILDCARD', 'DOMAIN-REGEX', 'GEOSITE',
    'IP-CIDR', 'IP-CIDR6', 'IP-SUFFIX', 'IP-ASN', 'GEOIP', 
    'SRC-GEOIP', 'SRC-IP-ASN', 'SRC-IP-CIDR', 'SRC-IP-SUFFIX',
    'DST-PORT', 'SRC-PORT',
    'IN-PORT', 'IN-TYPE', 'IN-USER', 'IN-NAME',
    'PROCESS-PATH', 'PROCESS-PATH-REGEX', 'PROCESS-NAME', 'PROCESS-NAME-REGEX',
    'UID', 'NETWORK', 'DSCP',
    'RULE-SET',
    'AND', 'OR', 'NOT', 'SUB-RULE',
    'MATCH'
}

# ================= 逻辑区域 =================

def download_rule_provider(url):
    """下载规则内容"""
    full_url = URL_PREFIX + url
    print(f"    ⬇️  正在下载: {full_url}")
    try:
        resp = requests.get(full_url, timeout=15)
        resp.raise_for_status()
        # 过滤空行和注释
        lines = [line.strip() for line in resp.text.splitlines() if line.strip() and not line.strip().startswith('#')]
        return lines
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        return []

def process_file(filename):
    if not os.path.exists(filename):
        print(f"❌ 找不到文件: {filename}")
        return

    print(f"📂 开始处理: {filename}")
    
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            yaml_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"    ❌ YAML 解析失败: {e}")
            return

    providers = yaml_data.get('rule-providers', {})
    current_rules = yaml_data.get('rules', [])

    if not providers or not current_rules:
        print("    ⚠️  未找到 rule-providers 或 rules，跳过...")
        return

    provider_cache = {}
    merged_rules = []
    
    print("    🔄 正在合并规则...")
    for rule in current_rules:
        # 1. 基础清洗：移除引号
        rule = rule.replace("'", "").replace('"', "")
        
        # 2. 分割规则以获取类型
        parts = [p.strip() for p in rule.split(',')]
        if not parts:
            continue
            
        rule_type = parts[0].upper() # 统一转为大写比较

        # 【核心过滤逻辑 1】检查本地规则是否在白名单内
        # 注意：AND/OR 等复杂逻辑规则可能包含逗号，这里只检查第一个单词是否合法
        # 如果是 complex payload (例如 AND,((DOMAIN...)))，parts[0] 依然是 AND，可以通过
        if rule_type not in VALID_RULE_TYPES:
            print(f"    ⚠️  跳过无效/不支持的本地规则类型: {rule_type}")
            continue

        if rule_type == 'RULE-SET':
            # 处理规则集引用
            if len(parts) < 3:
                continue
                
            provider_name = parts[1]
            policy_group = parts[2] # 获取策略组
            
            provider_info = providers.get(provider_name)
            if provider_info and 'url' in provider_info:
                url = provider_info['url']
                if provider_name not in provider_cache:
                    provider_cache[provider_name] = download_rule_provider(url)
                
                rule_lines = provider_cache[provider_name]
                
                for line in rule_lines:
                    # 清洗下载的内容
                    line = line.replace("'", "").replace('"', "")
                    line_parts = [p.strip() for p in line.split(',')]
                    
                    if not line_parts:
                        continue
                        
                    downloaded_rule_type = line_parts[0].upper()

                    # 【核心过滤逻辑 2】检查下载的规则是否在白名单内
                    if downloaded_rule_type not in VALID_RULE_TYPES:
                        # 默默跳过，不打印日志以免刷屏（很多老列表会有 USER-AGENT）
                        continue

                    # 处理 no-resolve
                    # Clash 逻辑：no-resolve 必须放在策略组之后
                    has_no_resolve = False
                    if 'no-resolve' in line_parts:
                        has_no_resolve = True
                        line_parts = [p for p in line_parts if p != 'no-resolve'] # 移除它
                    
                    # 重新组合前面的部分 (类型,值)
                    base_line = ",".join(line_parts)
                    
                    # 拼接逻辑： 类型,值,策略组,no-resolve(如果有)
                    if has_no_resolve:
                        merged_rules.append(f"- {base_line},{policy_group},no-resolve")
                    else:
                        merged_rules.append(f"- {base_line},{policy_group}")
            else:
                print(f"    ⚠️  找不到 Provider 定义或 URL: {provider_name}")
        else:
            # 对于非 RULE-SET 的普通规则（且已通过白名单检查），直接保留
            merged_rules.append(f"- {rule}")

    # ================= 文件写入 =================
    # 读取头部并写入新文件
    with open(filename, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    header_lines = []
    cut_indices = []
    for i, line in enumerate(raw_lines):
        if line.strip().startswith('rule-providers:') or line.strip().startswith('rules:'):
            cut_indices.append(i)
    
    cut_point = min(cut_indices) if cut_indices else len(raw_lines)
    header_lines = raw_lines[:cut_point]

    output_filename = filename.replace('.yaml', '_merge.yaml')
    if output_filename == filename:
        output_filename += "_merge"
        
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.writelines(header_lines)
        f.write("\n")
        f.write("rules:\n")
        for r in merged_rules:
            f.write(f"  {r}\n")
            
    print(f"    ✅ 生成文件: {output_filename} (共 {len(merged_rules)} 条规则)")

def main():
    for f in FILES_TO_PROCESS:
        process_file(f)

if __name__ == "__main__":
    main()
