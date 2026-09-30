#!/usr/bin/env python3
"""
递归补齐离线包的子依赖（BFS 遍历依赖树，过滤 extra 和 platform markers）。
用法: python3 resolve_deps.py <packages_dir> <requirements_file> [pip_whl] [index_url]
"""
import subprocess, sys, re, os, glob, zipfile

PACKAGES_DIR = sys.argv[1]
REQ_FILE = sys.argv[2]
INDEX_URL = sys.argv[4] if len(sys.argv) > 4 else "https://mirrors.aliyun.com/pypi/simple/"
TRUSTED_HOST = re.sub(r'https?://([^/:]+).*', r'\1', INDEX_URL)

PLATFORM = "win_amd64"
PY_VERSION = "3.12"

def normalize(name):
    return name.lower().replace('-', '_').replace('.', '_')

def get_available_pkgs():
    pkgs = {}
    for f in os.listdir(PACKAGES_DIR):
        if f.endswith(('.whl', '.tar.gz', '.zip')):
            name = normalize(re.split(r'-[\d]', f)[0])
            pkgs[name] = f
    return pkgs

def parse_requirements_extras():
    """从 requirements.txt 解析顶层包名和启用的 extras"""
    top_pkgs = {}
    global_extras = set()
    with open(REQ_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'([a-zA-Z0-9_.-]+)(\[([^\]]+)\])?', line)
            if m:
                pkg = normalize(m.group(1))
                top_pkgs[pkg] = True
                if m.group(3):
                    for extra in m.group(3).split(','):
                        global_extras.add(extra.strip())
    return top_pkgs, global_extras

def parse_whl_requires(whl_path):
    """返回 (包名, [(req_str, marker), ...])"""
    try:
        z = zipfile.ZipFile(whl_path)
        meta_files = [n for n in z.namelist() if n.endswith('METADATA')]
        if not meta_files:
            return None, []
        meta = z.read(meta_files[0]).decode()
        pkg_name = None
        requires = []
        for line in meta.split('\n'):
            if line.startswith('Name:'):
                pkg_name = line[5:].strip()
            elif line.startswith('Requires-Dist:'):
                requires.append(line[len('Requires-Dist:'):].strip())
        return pkg_name, requires
    except Exception:
        return None, []

def should_install(req, global_extras):
    """判断依赖是否应该安装"""
    if ';' not in req:
        return True
    marker = req.split(';', 1)[1].strip()
    if 'sys_platform != "win32"' in marker or "sys_platform != 'win32'" in marker:
        return False
    if 'sys_platform == "linux' in marker or 'sys_platform == "darwin' in marker:
        return False
    if 'implementation_name' in marker and 'cpython' not in marker:
        return True
    if 'extra ==' in marker or "extra == '" in marker:
        m = re.search(r'extra == ["\'](\w+)["\']', marker)
        if m and m.group(1) in global_extras:
            return True
        return False
    return True

def extract_pkg_name(req):
    return re.split(r'[<>=;!\[]', req)[0].strip()

def extract_version_spec(req):
    if ';' in req:
        req = req.split(';', 1)[0]
    m = re.match(r'[^<>=;!\[]*([<>=!~\[\]].*)', req)
    return m.group(1).strip() if m else ""

def download_pkg(pkg_name, version_spec):
    spec = f"{pkg_name}{version_spec}" if version_spec else pkg_name
    for attempt_spec in [spec, pkg_name]:
        cmd = [
            'pip3', 'download', '--no-deps', '--dest', PACKAGES_DIR,
            '--index-url', INDEX_URL, '--trusted-host', TRUSTED_HOST,
            '--python-version', PY_VERSION, '--platform', PLATFORM,
            '--only-binary', ':all:', attempt_spec
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            saved = [l for l in result.stdout.split('\n') if 'Saved' in l]
            if saved:
                return saved[0].strip()
    return None

def main():
    available = get_available_pkgs()
    top_pkgs, global_extras = parse_requirements_extras()
    print(f"已有包: {len(available)} 个, 顶层包: {len(top_pkgs)} 个, extras: {global_extras}")

    # BFS 队列：只从 requirements.txt 顶层包开始，不解析无关包
    queue = list(top_pkgs.keys())
    parsed = set()

    for round_num in range(1, 50):
        new_deps = []
        while queue:
            pkg = queue.pop(0)
            if pkg in parsed:
                continue
            parsed.add(pkg)
            # 找到这个包的 whl 文件
            whl_path = None
            for f in glob.glob(os.path.join(PACKAGES_DIR, '*.whl')):
                if normalize(re.split(r'-[\d]', os.path.basename(f))[0]) == pkg:
                    whl_path = f
                    break
            if not whl_path:
                continue
            _, requires = parse_whl_requires(whl_path)
            for req in requires:
                if not should_install(req, global_extras):
                    continue
                dep_name = normalize(extract_pkg_name(req))
                if dep_name not in available:
                    new_deps.append((dep_name, extract_pkg_name(req), extract_version_spec(req)))

        if not new_deps:
            print(f"第 {round_num} 轮: 所有子依赖已满足!")
            break

        print(f"第 {round_num} 轮: 发现 {len(new_deps)} 个缺失子依赖")
        for dep_norm, dep_name, version_spec in sorted(new_deps):
            if dep_norm in available:
                continue
            saved = download_pkg(dep_name, version_spec)
            if saved:
                print(f"  下载: {saved}")
                available = get_available_pkgs()
                queue.append(dep_norm)
            else:
                print(f"  失败: {dep_name}{version_spec} (可能无 win_amd64 wheel)")

    print(f"完成! 共有 {len(get_available_pkgs())} 个包")

if __name__ == '__main__':
    main()