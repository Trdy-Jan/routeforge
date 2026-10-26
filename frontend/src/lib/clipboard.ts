export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false // 非 HTTPS 页面或浏览器拒绝访问剪贴板
  }
}
