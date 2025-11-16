#!/usr/bin/env python3
"""
修复SSL证书问题 - 配置zerotrust证书
"""

import os
import ssl
import certifi
from pathlib import Path

def fix_ssl_certificates():
    """配置SSL证书以支持zerotrust VPN"""
    
    cert_file = Path.home() / "Downloads" / "certificate.crt"
    
    if not cert_file.exists():
        print(f"错误: 证书文件不存在: {cert_file}")
        print("请确保证书文件已下载到 ~/Downloads/certificate.crt")
        return False
    
    print(f"找到证书文件: {cert_file}")
    
    # 读取zerotrust证书
    with open(cert_file, 'r') as f:
        zerotrust_cert = f.read()
    
    # 读取系统证书
    system_cert_file = certifi.where()
    with open(system_cert_file, 'r') as f:
        system_certs = f.read()
    
    # 创建合并的证书文件
    merged_cert_file = Path.home() / ".hummingbot_certs.pem"
    with open(merged_cert_file, 'w') as f:
        f.write(system_certs)
        f.write("\n")
        f.write(zerotrust_cert)
    
    print(f"合并证书文件已创建: {merged_cert_file}")
    
    # 设置环境变量
    os.environ['SSL_CERT_FILE'] = str(merged_cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(merged_cert_file)
    
    print("SSL证书环境变量已设置:")
    print(f"  SSL_CERT_FILE={merged_cert_file}")
    print(f"  REQUESTS_CA_BUNDLE={merged_cert_file}")
    
    # 测试SSL连接
    try:
        import urllib.request
        import ssl
        
        # 创建SSL上下文
        context = ssl.create_default_context(cafile=str(merged_cert_file))
        
        # 测试连接
        url = "https://api.binance.com/api/v3/ping"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            print(f"\n✓ SSL连接测试成功: {url}")
            print(f"  状态码: {response.status}")
            return True
    except Exception as e:
        print(f"\n✗ SSL连接测试失败: {e}")
        return False


if __name__ == "__main__":
    print("="*80)
    print("修复SSL证书配置")
    print("="*80)
    
    if fix_ssl_certificates():
        print("\n" + "="*80)
        print("✓ SSL证书配置完成")
        print("="*80)
        print("\n使用方法:")
        print("  在运行回测前，先运行此脚本:")
        print("  python3 fix_ssl.py")
        print("\n或者设置环境变量:")
        print("  export SSL_CERT_FILE=~/.hummingbot_certs.pem")
        print("  export REQUESTS_CA_BUNDLE=~/.hummingbot_certs.pem")
    else:
        print("\n" + "="*80)
        print("✗ SSL证书配置失败")
        print("="*80)

