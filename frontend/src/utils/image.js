// 拍照后的图像几何计算。
//
// 这里刻意做成不依赖浏览器 API 的纯函数：预览是按容器宽度缩放显示的，
// 而裁剪必须换算回原图像素，坐标系搞错就会裁偏——所以这部分单独抽出来测。

/** 把选区限制在图像范围内，宽高至少为 1 像素。 */
export function clampRect(rect, size) {
  const x = Math.max(0, Math.min(Math.round(rect.x), size.width))
  const y = Math.max(0, Math.min(Math.round(rect.y), size.height))
  const width = Math.max(1, Math.min(Math.round(rect.width), size.width - x))
  const height = Math.max(1, Math.min(Math.round(rect.height), size.height - y))
  return { x: x, y: y, width: width, height: height }
}

/** 把显示坐标系的矩形换算到目标（原图）坐标系。 */
export function scaleRect(rect, fromSize, toSize) {
  if (!fromSize.width || !fromSize.height) {
    return { x: 0, y: 0, width: 0, height: 0 }
  }
  const scaleX = toSize.width / fromSize.width
  const scaleY = toSize.height / fromSize.height
  return clampRect({
    x: rect.x * scaleX,
    y: rect.y * scaleY,
    width: rect.width * scaleX,
    height: rect.height * scaleY,
  }, toSize)
}

/** 由拖拽的起点与终点得到规范化矩形（左上角 + 宽高）。 */
export function selectionToRect(start, end) {
  return {
    x: Math.min(start.x, end.x),
    y: Math.min(start.y, end.y),
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  }
}

/** 旋转若干度后的画布尺寸（只按 90 度的整数倍处理）。 */
export function rotateSize(size, degrees) {
  const normalized = ((Math.round(degrees) % 360) + 360) % 360
  if (normalized === 90 || normalized === 270) {
    return { width: size.height, height: size.width }
  }
  return { width: size.width, height: size.height }
}

/** 旋转后某个点在画布上的新位置；用于把裁剪框一起转过去。 */
export function rotatePoint(point, size, degrees) {
  const normalized = ((Math.round(degrees) % 360) + 360) % 360
  if (normalized === 90) {
    return { x: size.height - point.y, y: point.x }
  }
  if (normalized === 180) {
    return { x: size.width - point.x, y: size.height - point.y }
  }
  if (normalized === 270) {
    return { x: point.y, y: size.width - point.x }
  }
  return { x: point.x, y: point.y }
}

/** 生成不会重名的拍摄文件名。 */
export function captureFileName(index) {
  return 'camera-' + String(index).padStart(3, '0') + '.jpg'
}