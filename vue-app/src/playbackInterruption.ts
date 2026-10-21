export interface PlaybackPort {
  currentTime: number
  paused: boolean
  pause(): void
  play(): Promise<void>
}

export interface ResumePosition {
  currentPage: number
  currentTime: number
  wasPlaying: boolean
  sourceKey: string
}

export class PlaybackInterruption {
  private active: ResumePosition | null = null
  constructor(private media: PlaybackPort, private sourceKey: () => string) {}

  begin(currentPage: number): ResumePosition {
    if (this.active) throw new Error('已有问题正在处理，请先完成或取消')
    if (!Number.isInteger(currentPage) || currentPage < 1 || !Number.isFinite(this.media.currentTime)) {
      throw new Error('当前播放位置无效')
    }
    this.active = {currentPage, currentTime: this.media.currentTime,
      wasPlaying: !this.media.paused, sourceKey: this.sourceKey()}
    this.media.pause()
    return {...this.active}
  }

  get position(): ResumePosition | null { return this.active ? {...this.active} : null }

  restore(saved: ResumePosition): void {
    if (this.active || saved.sourceKey !== this.sourceKey() ||
        !Number.isInteger(saved.currentPage) || saved.currentPage < 1 ||
        !Number.isFinite(saved.currentTime) || saved.currentTime < 0 || typeof saved.wasPlaying !== 'boolean') {
      throw new Error('保存的课程播放位置无效')
    }
    this.active = {...saved}
    this.media.pause()
  }

  async resume(): Promise<boolean> {
    if (!this.active) return false
    const saved = this.active
    if (saved.sourceKey !== this.sourceKey()) {
      this.active = null
      return false
    }
    this.media.currentTime = saved.currentTime
    if (saved.wasPlaying) await this.media.play()
    this.active = null
    return true
  }

  discard(): void { this.active = null }
}
