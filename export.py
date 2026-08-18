import requests
import csv
import time
from collections import Counter

# ================= 配置区 =================
SHOPIFY_STORE = "your-store.myshopify.com"
ACCESS_TOKEN = "xxxxxxxxxxxxxxxx"          
METAFIELD_NAMESPACE = "custom"             # 你的元字段命名空间
METAFIELD_KEY = "google_custom_id"         # 你的元字段键名
API_VERSION = "2024-07"
# =========================================

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_graphql_query(query, variables=None):
    """发送 GraphQL 请求，处理限流和错误"""
    url = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": ACCESS_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=60)

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 5))
        print(f"触发限流，等待 {retry_after} 秒后重试...")
        time.sleep(retry_after)
        return run_graphql_query(query, variables)

    response.raise_for_status()
    return response.json()


def get_all_variant_metafields():
    """获取所有变体的 Google Custom ID"""
    all_variants = []
    cursor = None
    has_next_page = True

    while has_next_page:
        # 使用 metafield（单数）直接获取特定元字段
        query = """
        query GetVariants($cursor: String) {
          products(first: 250, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                variants(first: 250) {
                  edges {
                    node {
                      id
                      metafield(namespace: "%s", key: "%s") {
                        value
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """ % (METAFIELD_NAMESPACE, METAFIELD_KEY)

        variables = {"cursor": cursor}
        result = run_graphql_query(query, variables)

        if "errors" in result:
            print("GraphQL 查询错误:", result["errors"])
            break

        products_edges = result.get("data", {}).get("products", {}).get("edges", [])
        for product_edge in products_edges:
            variants_edges = product_edge["node"]["variants"]["edges"]
            for variant_edge in variants_edges:
                variant_node = variant_edge["node"]
                variant_gid = variant_node["id"]
                variant_id = variant_gid.split("/")[-1]  # 提取数字ID

                metafield_node = variant_node.get("metafield")  # 直接获取元字段对象
                value = metafield_node.get("value") if metafield_node else None

                all_variants.append({
                    "Variant ID": variant_id,
                    "Google Custom ID": value
                })

        page_info = result.get("data", {}).get("products", {}).get("pageInfo", {})
        has_next_page = page_info.get("hasNextPage", False)
        if has_next_page:
            cursor = page_info.get("endCursor")
            print(f"继续获取下一页，游标: {cursor}")
        else:
            print("所有数据获取完毕。")

    return all_variants


def mark_duplicates(variants_data):
    """标记重复值并打印报告"""
    id_counts = Counter(item['Google Custom ID'] for item in variants_data if item['Google Custom ID'] is not None)
    duplicates = {value: count for value, count in id_counts.items() if count > 1}
    if duplicates:
        print("\n⚠️ 发现重复的 Google Custom ID：")
        for value, count in duplicates.items():
            print(f"  - '{value}' 出现了 {count} 次")
    else:
        print("\n✅ 没有发现重复的 Google Custom ID。")

    for item in variants_data:
        val = item['Google Custom ID']
        item['是否重复'] = '是' if (val is not None and id_counts.get(val, 0) > 1) else '否'
    return variants_data


def save_to_csv(data, filename='variant_google_ids_with_duplicates.csv'):
    if not data:
        print("没有数据可保存。")
        return
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['Variant ID', 'Google Custom ID', '是否重复'])
        writer.writeheader()
        writer.writerows(data)
    print(f"\n✅ 数据已导出到 {filename}，共 {len(data)} 条记录。")


if __name__ == "__main__":
    print("开始导出变体的 Google Custom ID（使用 GraphQL metafield 单数查询）...")
    raw = get_all_variant_metafields()
    if raw:
        marked = mark_duplicates(raw)
        save_to_csv(marked)
        print("🎉 导出完成！")
    else:
        print("❌ 未获取到任何变体数据。")
