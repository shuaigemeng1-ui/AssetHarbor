// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

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

  it('keeps the 1080p content width and progressively expands on wider displays', () => {
    expectDeclaration(
      topLevelBlock(workspaceCss, ':root'),
      '--workspace-content-max',
      'clamp(1180px, calc(100% - 528px), 1800px)',
    )
    expectDeclaration(
      topLevelBlock(workspaceCss, '.workspace-main > .page-content'),
      'width',
      'min(var(--workspace-content-max), calc(100% - 56px))',
    )
    expectDeclaration(
      topLevelBlock(workspaceCss, '.workspace-main > .site-footer'),
      'width',
      'min(var(--workspace-content-max), calc(100% - 56px))',
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

  it('preserves the intentional 1080p grid and drawer breakpoints', () => {
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

    expectDeclaration(
      topLevelBlock(topLevelBlock(workspaceCss, '@media (max-width: 1320px)'), '.asset-grid'),
      'grid-template-columns',
      'repeat(3, minmax(0, 1fr))',
    )
    expectDeclaration(
      topLevelBlock(topLevelBlock(workspaceCss, '@media (max-width: 1160px)'), '.asset-grid'),
      'grid-template-columns',
      'repeat(4, minmax(0, 1fr))',
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
    const activeDrawerBreakpoint = /^\s*layoutMedia\s*=\s*window\.matchMedia\('\(max-width: 1160px\)'\)\s*;?\s*$/gm
    expect(withoutJsComments(galleryView).match(activeDrawerBreakpoint)).toHaveLength(1)
    expect(withoutJsComments(videoView).match(activeDrawerBreakpoint)).toHaveLength(1)
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
