export async function copyText(text: string): Promise<boolean> {
  // navigator.clipboard 仅在安全上下文（HTTPS / localhost）可用，
  // 通过 http://<局域网IP> 访问时为 undefined，需走 execCommand 兜底
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 浏览器拒绝授权时继续尝试兜底方案
    }
  }
  return legacyCopy(text)
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '0'
  textarea.style.left = '0'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  textarea.setSelectionRange(0, text.length)
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(textarea)
  }
}
