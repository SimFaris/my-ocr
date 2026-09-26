import { describe, expect, it } from 'vitest'
import { clampRect, captureFileName, rotatePoint, rotateSize, scaleRect, selectionToRect } from '../src/utils/image'

describe('clampRect', () => {
  it('把超出边界的矩形收回图像内', () => {
    expect(clampRect({ x: -10, y: -5, width: 500, height: 500 }, { width: 400, height: 300 }))
      .toEqual({ x: 0, y: 0, width: 400, height: 300 })
  })

  it('保证宽高至少为 1 像素', () => {
    const rect = clampRect({ x: 10, y: 10, width: 0, height: 0 }, { width: 100, height: 100 })
    expect(rect.width).toBe(1)
    expect(rect.height).toBe(1)
  })
})

describe('scaleRect', () => {
  it('把预览坐标换算成原图像素', () => {
    // 预览宽 400，原图宽 1600：放大 4 倍
    const rect = { x: 100, y: 50, width: 200, height: 100 }
    expect(scaleRect(rect, { width: 400, height: 300 }, { width: 1600, height: 1200 }))
      .toEqual({ x: 400, y: 200, width: 800, height: 400 })
  })

  it('预览与原图同尺寸时保持不变', () => {
    // 注意选区内必须完全落在图像里：超出部分会被 clampRect 收回去
    const rect = { x: 12, y: 34, width: 56, height: 60 }
    expect(scaleRect(rect, { width: 100, height: 100 }, { width: 100, height: 100 })).toEqual(rect)
  })

  it('选区超出图像时按边界收敛', () => {
    const rect = scaleRect({ x: 12, y: 34, width: 56, height: 78 },
      { width: 100, height: 100 }, { width: 100, height: 100 })
    expect(rect).toEqual({ x: 12, y: 34, width: 56, height: 66 })
  })

  it('尺寸为 0 时返回空矩形而不是 NaN', () => {
    expect(scaleRect({ x: 1, y: 1, width: 1, height: 1 },
      { width: 0, height: 0 }, { width: 100, height: 100 }))
      .toEqual({ x: 0, y: 0, width: 0, height: 0 })
  })

  it('换算结果不会越界', () => {
    const rect = scaleRect({ x: 390, y: 290, width: 50, height: 50 },
      { width: 400, height: 300 }, { width: 800, height: 600 })
    expect(rect.x + rect.width).toBeLessThanOrEqual(800)
    expect(rect.y + rect.height).toBeLessThanOrEqual(600)
  })
})

describe('selectionToRect', () => {
  it('从右下往左上拖也能得到正确矩形', () => {
    expect(selectionToRect({ x: 300, y: 200 }, { x: 100, y: 50 }))
      .toEqual({ x: 100, y: 50, width: 200, height: 150 })
  })
})

describe('rotateSize 与 rotatePoint', () => {
  it('90 度与 270 度交换宽高', () => {
    expect(rotateSize({ width: 800, height: 600 }, 90)).toEqual({ width: 600, height: 800 })
    expect(rotateSize({ width: 800, height: 600 }, 270)).toEqual({ width: 600, height: 800 })
    expect(rotateSize({ width: 800, height: 600 }, 180)).toEqual({ width: 800, height: 600 })
    expect(rotateSize({ width: 800, height: 600 }, 360)).toEqual({ width: 800, height: 600 })
  })

  it('负角度按等价正角度处理', () => {
    expect(rotateSize({ width: 800, height: 600 }, -90)).toEqual({ width: 600, height: 800 })
  })

  it('顺时针 90 度后左上角跑到右上角', () => {
    // 画布 800x600 顺时针转 90 度后是 600x800，(0,0) 应落到 (600,0)
    expect(rotatePoint({ x: 0, y: 0 }, { width: 800, height: 600 }, 90)).toEqual({ x: 600, y: 0 })
  })

  it('旋转 360 度等价于不变', () => {
    expect(rotatePoint({ x: 5, y: 9 }, { width: 800, height: 600 }, 360)).toEqual({ x: 5, y: 9 })
  })
})

describe('captureFileName', () => {
  it('按序号补零，便于排序', () => {
    expect(captureFileName(1)).toBe('camera-001.jpg')
    expect(captureFileName(42)).toBe('camera-042.jpg')
  })
})