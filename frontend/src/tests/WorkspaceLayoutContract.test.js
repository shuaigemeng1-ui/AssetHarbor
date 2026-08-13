// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspaceCss = readFileSync(new URL('../workspace.css', import.meta.url), 'utf8')
const collectionsView = readFileSync(new URL('../components/CollectionsView.vue', import.meta.url), 'utf8')
const galleryView = readFileSync(new URL('../components/GalleryView.vue', import.meta.url), 'utf8')
const videoView = readFileSync(new URL('../components/VideoView.vue', import.meta.url), 'utf8')
const mainEntry = readFileSync(new URL('../main.js', import.meta.url), 'utf8')
const collectionsCss = collectionsView.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] || ''

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
