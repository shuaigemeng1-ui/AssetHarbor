// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { WORKSPACE_DRAWER_MAX_WIDTH, WORKSPACE_DRAWER_MEDIA_QUERY } from '../utils/layout'

const workspaceCss = readFileSync(new URL('../workspace.css', import.meta.url), 'utf8')
const baseCss = readFileSync(new URL('../style.css', import.meta.url), 'utf8')
const collectionsView = readFileSync(new URL('../components/CollectionsView.vue', import.meta.url), 'utf8')
const galleryView = readFileSync(new URL('../components/GalleryView.vue', import.meta.url), 'utf8')
const videoView = readFileSync(new URL('../components/VideoView.vue', import.meta.url), 'utf8')
const teamsView = readFileSync(new URL('../components/TeamsView.vue', import.meta.url), 'utf8')
const mainEntry = readFileSync(new URL('../main.js', import.meta.url), 'utf8')
const collectionsCss = collectionsView.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] || ''
const teamsCss = teamsView.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] || ''

const readableComponentStyles = [
  'AccountView.vue',
  'AdminView.vue',
  'AuthView.vue',
  'BaseModal.vue',
  'CollectionPickerModal.vue',
  'CollectionsView.vue',
  'HomeView.vue',
  'ImageInspector.vue',
  'ImageResult.vue',
  'TeamsView.vue',
  'UploadCenterView.vue',
  'UploadDropzone.vue',
  'VideoCard.vue',
  'VideoInspector.vue',
].map(name => ({
  name,
  source: readFileSync(new URL(`../components/${name}`, import.meta.url), 'utf8'),
}))

function withoutComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, '')
}

function matchingBrace(source, openingBrace) {
  let depth = 0
  let quote = null
  for (let index = openingBrace; index < source.length; index += 1) {
    const character = source[index]
    if (quote) {
      if (character === '\\') index += 1
      else if (character === quote) quote = null
      continue
    }
    if (character === '"' || character === "'") {
      quote = character
      continue
    }
    if (character === '{') depth += 1
    if (character === '}') {
      depth -= 1
      if (depth === 0) return index
    }
  }
  throw new Error(`Unclosed CSS block at ${openingBrace}`)
}

function topLevelBlocks(source, prelude) {
  const css = withoutComments(source)
  const blocks = []
  let depth = 0
  let quote = null
  for (let index = 0; index < css.length; index += 1) {
    const character = css[index]
    if (quote) {
      if (character === '\\') index += 1
      else if (character === quote) quote = null
      continue
    }
    if (character === '"' || character === "'") {
      quote = character
      continue
    }
    if (character === '{') {
      depth += 1
      continue
    }
    if (character === '}') {
      depth -= 1
      continue
    }
    if (depth !== 0 || !css.startsWith(prelude, index)) continue

    let previous = index - 1
    while (previous >= 0 && /\s/.test(css[previous])) previous -= 1
    if (previous >= 0 && !['{', '}', ';'].includes(css[previous])) continue

    let openingBrace = index + prelude.length
    while (/\s/.test(css[openingBrace])) openingBrace += 1
    if (css[openingBrace] !== '{') continue
    const closingBrace = matchingBrace(css, openingBrace)
    blocks.push(css.slice(openingBrace + 1, closingBrace))
    index = closingBrace
  }
  return blocks
}

function topLevelBlock(source, prelude) {
  const blocks = topLevelBlocks(source, prelude)
  expect(blocks, `Expected one top-level block for ${prelude}`).toHaveLength(1)
  return blocks[0]
}

function expectDeclaration(block, property, expectedValue) {
  const declarationPattern = /(?:^|;)\s*([\w-]+)\s*:\s*([^;]+)(?=;|$)/g
  const values = [...block.matchAll(declarationPattern)]
    .filter(match => match[1] === property)
    .map(match => match[2].trim())
  expect(values, `Expected one effective ${property} declaration`).toEqual([expectedValue])
}

function withoutJsComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split(/\r?\n/)
    .filter(line => !line.trimStart().startsWith('//'))
    .join('\n')
}

describe('responsive workspace layout contract', () => {
  it('uses a readable semantic type scale across shared workspace surfaces', () => {
    const root = topLevelBlock(baseCss, ':root')
    expectDeclaration(root, '--font-micro', '11px')
    expectDeclaration(root, '--font-caption', '12px')
    expectDeclaration(root, '--font-secondary', '13px')
    expectDeclaration(root, '--font-body', '14px')
    expectDeclaration(root, '--font-control', '14px')
    expectDeclaration(root, '--font-panel', '16px')
    expectDeclaration(root, '--font-page', 'clamp(26px, 2vw, 30px)')
    expect(root).toContain('font: 16px/1.55')

    expectDeclaration(topLevelBlock(workspaceCss, '.side-nav button'), 'font-size', 'var(--font-control)')
    expectDeclaration(topLevelBlock(workspaceCss, '.workspace-context small'), 'font-size', 'var(--font-caption)')
    expectDeclaration(topLevelBlock(workspaceCss, '.upload-activity'), 'font-size', 'var(--font-caption)')
    expectDeclaration(topLevelBlock(baseCss, '.queue-meta'), 'font-size', 'var(--font-caption)')
    expectDeclaration(topLevelBlock(baseCss, '.data-table'), 'font-size', 'var(--font-body)')

    const activeUploadHover = topLevelBlock(workspaceCss, '.side-nav .nav-upload-center.active:hover')
    expectDeclaration(activeUploadHover, 'background', 'var(--accent-soft)')
    expectDeclaration(activeUploadHover, 'color', 'var(--accent)')
  })

  it('does not regress component text below the 11px readability floor', () => {
    for (const { name, source } of readableComponentStyles) {
      const styles = [...source.matchAll(/<style(?:\s+scoped)?>([\s\S]*?)<\/style>/g)]
        .map(match => withoutComments(match[1]))
        .join('\n')
      const undersized = [...styles.matchAll(/(?:font-size\s*:\s*|font\s*:[^;{}]*?\s)(\d+(?:\.\d+)?)px\b/g)]
        .map(match => Number(match[1]))
        .filter(size => size < 11)
      expect(undersized, `${name} contains text below 11px`).toEqual([])
    }
  })

  it('keeps mobile form controls at a zoom-safe readable size', () => {
    const mobileBase = topLevelBlock(baseCss, '@media (max-width: 760px)')
    expectDeclaration(topLevelBlock(mobileBase, 'input,\n  select,\n  textarea'), 'font-size', '16px !important')
  })

  it('keeps team member management actions horizontal in the desktop sidebar', () => {
    const memberActions = topLevelBlock(teamsCss, '.member-actions')
    expectDeclaration(memberActions, 'width', 'max-content')
    expectDeclaration(memberActions, 'flex-wrap', 'nowrap')
    expectDeclaration(memberActions, 'white-space', 'nowrap')

    const actionButton = topLevelBlock(teamsCss, '.member-actions button')
    expectDeclaration(actionButton, 'flex', '0 0 auto')
    expectDeclaration(actionButton, 'white-space', 'nowrap')
  })

  it('uses the available workspace width and caps ultra-wide content', () => {
    expectDeclaration(
      topLevelBlock(workspaceCss, ':root'),
      '--workspace-content-max',
      '1800px',
    )
    expectDeclaration(
      topLevelBlock(workspaceCss, '.workspace-main > .page-content'),
      'width',
      'min(var(--workspace-content-max), calc(100% - 56px))',
    )
    expectDeclaration(topLevelBlock(workspaceCss, '.workspace-main > .page-content'), 'max-width', 'none')
    expectDeclaration(
      topLevelBlock(workspaceCss, '.workspace-main > .site-footer'),
      'width',
      'min(var(--workspace-content-max), calc(100% - 56px))',
    )
    expectDeclaration(topLevelBlock(workspaceCss, '.workspace-main > .site-footer'), 'max-width', 'none')
  })

  it('keeps the app viewport-wide and leaves vertical scrolling to the document', () => {
    const widthRoots = [
      ['html', topLevelBlock(baseCss, 'html')],
      ['body', topLevelBlock(baseCss, 'body')],
      ['#app', topLevelBlock(baseCss, '#app')],
      ['.app-shell', topLevelBlock(baseCss, '.app-shell')],
      ['.workspace-shell', topLevelBlock(workspaceCss, '.workspace-shell')],
      ['.workspace-main', topLevelBlock(workspaceCss, '.workspace-main')],
    ]
    const nestedScrollOwner = /(?:^|;)\s*overflow(?:-[xy])?\s*:/
    const fixedViewportHeight = /(?:^|;)\s*height\s*:\s*100(?:d|s|l)?vh\b/

    for (const [selector, block] of widthRoots) {
      expectDeclaration(block, 'width', '100%')
      expectDeclaration(block, 'max-width', 'none')
      expect(block, `${selector} must leave scrolling to the document`).not.toMatch(nestedScrollOwner)
      expect(block, `${selector} must grow with content instead of clipping at the initial viewport`).not.toMatch(fixedViewportHeight)
    }

    expectDeclaration(
      topLevelBlock(workspaceCss, '.workspace-shell'),
      'grid-template-columns',
      '232px minmax(0, 1fr)',
    )

    const desktopWorkspace = topLevelBlock(workspaceCss, '@media (min-width: 861px)')
    const ordinaryMain = topLevelBlock(
      desktopWorkspace,
      '.workspace-main:not(.workspace-main-library):not(.workspace-main-full)',
    )
    expectDeclaration(ordinaryMain, 'display', 'grid')
    expectDeclaration(ordinaryMain, 'grid-template-rows', 'auto minmax(0, 1fr) auto')
    expectDeclaration(ordinaryMain, 'min-height', '100vh')
    expect(ordinaryMain, 'desktop workspace must not become a nested scroller').not.toMatch(nestedScrollOwner)
    expect(ordinaryMain, 'desktop workspace must grow beyond the initial viewport').not.toMatch(fixedViewportHeight)
    expectDeclaration(
      topLevelBlock(
        desktopWorkspace,
        '.workspace-main:not(.workspace-main-library):not(.workspace-main-full) > .page-content',
      ),
      'min-height',
      '0',
    )
  })

  it('keeps full-width media libraries outside the ordinary page cap', () => {
    expectDeclaration(topLevelBlock(workspaceCss, '.workspace-main-library > .page-content'), 'width', '100%')

    const mobileWorkspace = topLevelBlock(workspaceCss, '@media (max-width: 860px)')
    expectDeclaration(
      topLevelBlock(mobileWorkspace, '.workspace-main > .page-content'),
      'width',
      'min(100% - 30px, 1180px)',
    )
    expectDeclaration(
      topLevelBlock(mobileWorkspace, '.workspace-main-library > .page-content'),
      'width',
      '100%',
    )
  })

  it('adds density only inside the wide-display media block', () => {
    const wideWorkspace = topLevelBlock(workspaceCss, '@media (min-width: 1921px)')
    expectDeclaration(
      topLevelBlock(
        wideWorkspace,
        '.workspace-main-library .asset-library:not(.asset-library-embedded) .asset-grid',
      ),
      'grid-template-columns',
      'repeat(auto-fill, minmax(300px, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(wideWorkspace, '.asset-library-embedded .asset-grid'),
      'grid-template-columns',
      'repeat(auto-fill, minmax(270px, 1fr))',
    )

    const wideCollections = topLevelBlock(collectionsCss, '@media (min-width: 1921px)')
    expectDeclaration(
      topLevelBlock(wideCollections, '.collection-media-grid'),
      'grid-template-columns',
      'repeat(auto-fill, minmax(280px, 1fr))',
    )
  })

  it('switches drawers before the sidebar leaves less than 1160px for content', () => {
    expectDeclaration(
      topLevelBlock(workspaceCss, '.asset-grid'),
      'grid-template-columns',
      'repeat(4, minmax(0, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(workspaceCss, '.asset-library-embedded .asset-grid'),
      'grid-template-columns',
      'repeat(3, minmax(0, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(collectionsCss, '.collection-media-grid'),
      'grid-template-columns',
      'repeat(3, minmax(0, 1fr))',
    )

    const compactInlineGrid = topLevelBlock(
      workspaceCss,
      '@media (min-width: 1409px) and (max-width: 1573px)',
    )
    expectDeclaration(
      topLevelBlock(
        compactInlineGrid,
        '.workspace-main-library .asset-library:not(.asset-library-embedded) .asset-grid',
      ),
      'grid-template-columns',
      'repeat(3, minmax(0, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(
        topLevelBlock(workspaceCss, `@media (max-width: ${WORKSPACE_DRAWER_MAX_WIDTH}px)`),
        '.asset-grid',
      ),
      'grid-template-columns',
      'repeat(auto-fill, minmax(220px, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(topLevelBlock(workspaceCss, '@media (max-width: 960px)'), '.asset-grid'),
      'grid-template-columns',
      'repeat(3, minmax(0, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(topLevelBlock(workspaceCss, '@media (max-width: 620px)'), '.asset-grid'),
      'grid-template-columns',
      'repeat(2, minmax(0, 1fr))',
    )
    expect(WORKSPACE_DRAWER_MAX_WIDTH - 232 - 16).toBe(1160)
    expect(WORKSPACE_DRAWER_MEDIA_QUERY).toBe('(max-width: 1408px)')
    const drawerWorkspace = topLevelBlock(workspaceCss, '@media (max-width: 1408px)')
    expectDeclaration(topLevelBlock(drawerWorkspace, '.asset-library'), 'grid-template-columns', '1fr')
    expectDeclaration(
      topLevelBlock(drawerWorkspace, '.asset-library:not(.asset-library-embedded) > .image-inspector'),
      'position',
      'fixed !important',
    )
    expectDeclaration(
      topLevelBlock(drawerWorkspace, '.asset-library:not(.asset-library-embedded).inspector-open > .image-inspector'),
      'transform',
      'translateX(0)',
    )
    const activeDrawerQuery = /window\.matchMedia\(WORKSPACE_DRAWER_MEDIA_QUERY\)/g
    expect(withoutJsComments(galleryView).match(activeDrawerQuery)).toHaveLength(1)
    expect(withoutJsComments(videoView).match(activeDrawerQuery)).toHaveLength(1)
    expect(withoutJsComments(teamsView).match(activeDrawerQuery)).toHaveLength(1)
    const drawerTeams = topLevelBlock(teamsCss, '@media (max-width: 1408px)')
    expectDeclaration(topLevelBlock(drawerTeams, '.teams-layout'), 'grid-template-columns', 'minmax(0, 1fr)')
    expectDeclaration(topLevelBlock(drawerTeams, '.members-panel'), 'position', 'fixed')
    expectDeclaration(topLevelBlock(drawerTeams, '.members-panel.open'), 'transform', 'translateX(0)')
    expectDeclaration(topLevelBlock(drawerTeams, ".members-panel[aria-hidden='true']"), 'visibility', 'hidden')
    expect([workspaceCss, galleryView, videoView, teamsView].join('\n')).not.toContain('(max-width: 1160px)')
  })

  it('preserves the stylesheet cascade used by workspace overrides', () => {
    const activeMainEntry = withoutJsComments(mainEntry)
    const baseStyles = activeMainEntry.search(/^\s*import\s+['"]\.\/style\.css['"]\s*;?\s*$/m)
    const workspaceStyles = activeMainEntry.search(/^\s*import\s+['"]\.\/workspace\.css['"]\s*;?\s*$/m)
    expect(baseStyles).toBeGreaterThanOrEqual(0)
    expect(workspaceStyles).toBeGreaterThanOrEqual(0)
    expect(baseStyles).toBeLessThan(workspaceStyles)
  })
})
