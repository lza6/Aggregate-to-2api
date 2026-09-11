// v12.0.1：DAG SVG 分层图 + 推理轨迹面板测试（渲染节点/状态着色/点击选中/黑匣子全文）。
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DagGraph, DagTrace, STATUS_META } from '../components/DagGraph';
import type { DagNodePublic } from '../api/agent';

function makeNode(overrides: Partial<DagNodePublic>): DagNodePublic {
  return {
    id: 'n1',
    kind: 'llm',
    status: 'pending',
    depends_on: [],
    prompt: null,
    model: null,
    result: null,
    error: null,
    attempt: 0,
    duration_ms: 0,
    created_at: 1,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

const nodes: DagNodePublic[] = [
  makeNode({ id: 'prep', kind: 'scene', depends_on: [], prompt: '识别场景' }),
  makeNode({ id: 'gen', kind: 'llm', status: 'succeeded', depends_on: ['prep'], prompt: '生成主图', result: 'ok-img', duration_ms: 1234, attempt: 1 }),
  makeNode({ id: 'check', kind: 'critic', status: 'failed', depends_on: ['gen'], error: '质检不通过', attempt: 2 }),
];

describe('DagGraph', () => {
  it('渲染全部节点（id + kind 徽标）且 SVG 含状态着色边', () => {
    const { container } = render(<DagGraph nodes={nodes} />);
    expect(screen.getByText('prep')).toBeTruthy();
    expect(screen.getByText('gen')).toBeTruthy();
    expect(screen.getByText('check')).toBeTruthy();
    expect(screen.getAllByText('llm').length).toBeGreaterThan(0);
    // 边按子节点状态着色（failed → 红）
    const edges = container.querySelectorAll('.dag-svg-edge');
    expect(edges.length).toBe(2);
    expect((edges[1] as SVGPathElement).getAttribute('stroke')).toBe(STATUS_META.failed.color);
  });

  it('点击节点出现选中态并弹出推理轨迹（prompt/result/error 全文）', () => {
    const { container } = render(<DagGraph nodes={nodes} />);
    expect(screen.queryByText(/输入 Prompt/)).toBeNull();
    fireEvent.click(screen.getByText('gen').closest('g') as SVGGElement);
    expect(container.querySelector('.dag-svg-node.selected')).toBeTruthy();
    expect(screen.getByRole('region', { name: /节点 gen 推理轨迹/ })).toBeTruthy();
    expect(screen.getByText('生成主图')).toBeTruthy();
    expect(screen.getByText('ok-img')).toBeTruthy();
    expect(screen.getByText('耗时 1.23s')).toBeTruthy();
  });

  it('点击失败节点展示错误全文（红）与 attempt', () => {
    render(<DagGraph nodes={nodes} />);
    fireEvent.click(screen.getByText('check').closest('g') as SVGGElement);
    expect(screen.getByText('质检不通过')).toBeTruthy();
    expect(screen.getByText('尝试 #2')).toBeTruthy();
  });

  it('运行中节点带呼吸动画 class（dag-node-running）', () => {
    render(
      <DagGraph nodes={[makeNode({ id: 'r', status: 'running' })]} />,
    );
    expect(document.querySelector('.dag-node-running')).toBeTruthy();
  });

  it('空节点列表不渲染', () => {
    const { container } = render(<DagGraph nodes={[]} />);
    expect(container.querySelector('.dag-svg')).toBeNull();
  });
});

describe('DagTrace', () => {
  it('未选中时展示引导文案；pending 且无内容展示「尚未执行」', () => {
    const first = render(<DagTrace node={null} />);
    expect(screen.getByText(/点击上方节点/)).toBeTruthy();
    first.unmount();
    render(<DagTrace node={makeNode({ id: 'p' })} />);
    expect(screen.getByText('该节点尚未执行')).toBeTruthy();
  });
});
