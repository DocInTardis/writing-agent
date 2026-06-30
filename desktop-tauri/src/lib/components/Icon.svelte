<script lang="ts">
  const ICON_PATHS = {
    chat: 'M4 6.5a2.5 2.5 0 0 1 2.5-2.5h11A2.5 2.5 0 0 1 20 6.5v7A2.5 2.5 0 0 1 17.5 16H12l-4 4v-4H6.5A2.5 2.5 0 0 1 4 13.5v-7ZM8 8h8M8 11h6',
    library: 'M5 5.5A1.5 1.5 0 0 1 6.5 4h9A1.5 1.5 0 0 1 17 5.5v13a.5.5 0 0 1-.8.4L12 16l-4.2 2.9a.5.5 0 0 1-.8-.4v-13ZM8 8h6M8 11h6',
    editor: 'M5 19h4l9-9-4-4-9 9v4Zm7-11 4 4M5 19h14',
    canvas: 'M4 4h7v7H4V4Zm9 0h7v5h-7V4ZM4 13h5v7H4v-7Zm7 3h9v4h-9v-4Z',
    save: 'M6 4h9l3 3v13H6V4Zm3 0v5h6V4M9 20v-6h6v6',
    doc: 'M7 4h7l4 4v12H7V4Zm7 0v4h4M9 12h6M9 15h6',
    pdf: 'M6 4h7l4 4v12H6V4Zm7 0v4h4M8.5 15.5v-3h1.6a1.1 1.1 0 1 1 0 2.2H8.5Zm4.2 0v-3H14c.9 0 1.6.7 1.6 1.5s-.7 1.5-1.6 1.5h-1.3Z',
    ai: 'M12 3l1.7 3.6L17 8.3l-3.3 1.7L12 13.7 10.3 10 7 8.3l3.3-1.7L12 3Zm6 10.5.9 2 2 .9-2 .9-.9 2-.9-2-2-.9 2-.9.9-2ZM5.5 13l.8 1.8L8 15.6l-1.7.8L5.5 18l-.8-1.6L3 15.6l1.7-.8.8-1.8Z',
    shield: 'M12 3l7 3v5c0 4.7-2.8 8-7 10-4.2-2-7-5.3-7-10V6l7-3Zm-3 8 2 2 4-4',
    star: 'm12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.2 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3Z',
    upload: 'M12 15V6m0 0-3 3m3-3 3 3M5 16.5V19h14v-2.5',
    search: 'm20 20-4.2-4.2M10.8 17a6.2 6.2 0 1 1 0-12.4 6.2 6.2 0 0 1 0 12.4Z',
    grid: 'M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z',
    masonry: 'M4 4h7v5H4V4Zm9 0h7v8h-7V4ZM4 11h7v9H4v-9Zm9 3h7v6h-7v-6Z',
    list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
    select: 'M5 12l4 4L19 6',
    batch: 'M4 5h6v6H4V5Zm10 0h6v6h-6V5ZM4 13h6v6H4v-6Zm10 2h6v4h-6v-4Z',
    eye: 'M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Zm9.5 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
    eyeOff: 'm3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M7.2 7.3A13.9 13.9 0 0 1 12 6c6.1 0 9.5 6 9.5 6a17.3 17.3 0 0 1-4.2 4.6M5.1 9.8A17.7 17.7 0 0 0 2.5 12s3.4 6 9.5 6c1.4 0 2.7-.3 3.9-.8',
    undo: 'M8 8H4v4M4 8a8 8 0 1 1-.2 8.1',
    redo: 'M16 8h4v4M20 8a8 8 0 1 0 .2 8.1',
    copy: 'M9 9h9v11H9V9Zm-3 6H5a1 1 0 0 1-1-1V5h9a1 1 0 0 1 1 1v1',
    cut: 'm14 14 6 6M20 14l-6 6M4 7a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0Zm0 10a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0ZM8.5 8.8l7 6.4',
    paste: 'M8 4h8v3H8V4Zm-2 3h12v13H6V7Zm3 4h6M9 14h6',
    clear: 'M4 7h16M9 7V5h6v2m-8 0 1 12h8l1-12M10 10v6M14 10v6',
    bold: 'M8 5h6a3 3 0 0 1 0 6H8V5Zm0 6h7a3 3 0 1 1 0 6H8v-6Z',
    italic: 'M10 4h8M6 20h8M14 4 10 20',
    underline: 'M7 4v6a5 5 0 1 0 10 0V4M6 20h12',
    h1: 'M5 5v14M11 5v14M5 12h6M16 6h3v13M16 6h4',
    h2: 'M5 5v14M10 5v14M5 12h5M15 9a3 3 0 1 1 6 0c0 2-1.2 3-3 4.5L15 16h6',
    quote: 'M7 8h5v8H5v-5l2-3Zm10 0h2v8h-5v-5l3-3Z',
    code: 'm8 8-4 4 4 4m8-8 4 4-4 4',
    listBullet: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
    listNumber: 'M6 6H4l2-2v6M8 6h12M4 12h2a2 2 0 0 1 0 4H4m4-4h12M4 20h3l-1.5-2 1.5-2M8 20h12',
    diagram: 'M5 6h5v4H5V6Zm9 0h5v4h-5V6ZM9 14h6v4H9v-4Zm1-4 2 4m2-4-2 4',
    cite: 'M7 7h6v4H7V7Zm-2 4h2v6h6v2H5v-8Zm8 0h6v8h-8v-2h6v-6Z',
    play: 'M8 6v12l10-6-10-6Z',
    stop: 'M7 7h10v10H7V7Z',
    resume: 'M6 12a6 6 0 1 0 2-4.5M6 4v4h4',
    book: 'M5 5a2 2 0 0 1 2-2h12v16H7a2 2 0 0 0-2 2V5Zm2 0v14',
    chart: 'M5 19V9m6 10V5m6 14v-7',
    clock: 'M12 6v6l4 2m4-2a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
    tag: 'm20 12-8 8-8-8V5h7l9 7Z',
    spark: 'M12 4l1.6 3.4L17 9l-3.4 1.6L12 14l-1.6-3.4L7 9l3.4-1.6L12 4Z',
    open: 'M14 4h6v6m0-6-9 9M5 8v11h11',
    clearSelection: 'M5 5l14 14M19 5 5 19'
  } as const

  export type IconName = keyof typeof ICON_PATHS

  export let name: IconName = 'spark'
  export let size = 16
  export let className = ''
  export let decorative = true
  export let label = ''

  $: d = ICON_PATHS[name] || ICON_PATHS.spark
  $: px = Math.max(12, Math.min(24, Number(size || 16)))
  $: ariaLabel = decorative ? undefined : label || name
</script>

<span
  class={`wa-icon ${className}`.trim()}
  aria-hidden={decorative}
  aria-label={ariaLabel}
>
  <svg
    viewBox="0 0 24 24"
    width={px}
    height={px}
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    focusable="false"
  >
    <path d={d}></path>
  </svg>
</span>

<style>
  .wa-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  .wa-icon :global(svg) {
    display: block;
    stroke: currentColor;
    stroke-width: 1.85;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
</style>
