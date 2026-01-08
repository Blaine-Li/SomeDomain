import requests
import yaml
import os

# ================= 配置区域 =================

# 1. 这里填写你仓库里原本的 Clash 配置文件名
# 脚本会读取这个文件，根据里面的 rule-providers 下载内容
FILES_TO_PROCESS = [
    'clashstga.yaml'
]

# GitHub Proxy (可选)
URL_PREFIX = "" 

# ================= 逻辑区域 =================

def download_rule_provider(url):
    """下载规则内容"""
    full_url = URL_PREFIX + url
    print(f"    ⬇️  正在下载: {full_url}")
    try:
        resp = requests.get(full_url, timeout=15)
        resp.raise_for_status()
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
        parts = [p.strip() for p in rule.split(',')]
        rule_type = parts[0]
        
        if rule_type == 'RULE-SET':
            provider_name = parts[1]
            policy_group = parts[2]
            
            provider_info = providers.get(provider_name)
            if provider_info and 'url' in provider_info:
                url = provider_info['url']
                if provider_name not in provider_cache:
                    provider_cache[provider_name] = download_rule_provider(url)
                
                rule_lines = provider_cache[provider_name]
                for line in rule_lines:
                    merged_rules.append(f"- {line},{policy_group}")
            else:
                print(f"    ⚠️  找不到 Provider 定义或 URL: {provider_name}")
        else:
            merged_rules.append(f"- {rule}")

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
