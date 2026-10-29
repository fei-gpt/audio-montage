"""Project policy, automatic history and a single resumable workflow entry."""
from pathlib import Path
from types import SimpleNamespace
import shutil

from montage import read, save


def archive(path):
    path = Path(path)
    if not path.exists():
        return
    folder = path.parent / 'history'
    folder.mkdir(exist_ok=True)
    n = 1
    dest = folder / f'{path.stem}-{n}{path.suffix}'
    while dest.exists():
        n += 1
        dest = folder / f'{path.stem}-{n}{path.suffix}'
    shutil.copy2(path, dest)


def effective_shot(root, shot):
    config = read(Path(root) / 'project.json')
    return dict(shot, product_model=shot.get('product_model') or config.get('product_model'))


def set_product(args):
    path = Path(args.project).resolve() / 'project.json'
    config = read(path)
    archive(path)
    config['product_model'] = args.model
    save(path, config)
    print('已保存项目产品型号；需要重新生成候选或方案，已有选片仍须按新产品复核。')


def flow(args):
    root = Path(args.project).resolve()
    if args.stage == 'plan':
        from planner import auto_plan
        auto_plan(SimpleNamespace(project=str(root), database=args.database,
                                  max_parts=4, min_part=0.8, min_score=0.35))
    elif args.stage == 'apply':
        from planner import apply_plan
        apply_plan(SimpleNamespace(project=str(root), proposal=str(root / 'plans/proposal.json')))
    elif args.stage in {'preview', 'final'}:
        from montage import render, review
        render(SimpleNamespace(project=str(root), final=args.stage == 'final'))
        review(SimpleNamespace(project=str(root), final=args.stage == 'final'))
    else:
        config = read(root / 'project.json')
        plan = root / 'plans/edit.json'
        shots = read(plan)['shots'] if plan.exists() else []
        print({'product_model': config.get('product_model'), 'shots': len(shots),
               'missing_selection': sum(not s.get('selection') for s in shots),
               'pending_review': sum(s.get('reviewed') is not True for s in shots),
               'stages': ['plan', 'apply', 'preview', 'final'],
               'note': '状态不代表已完成内容或媒体校验；审核仍由实际观察完成。'})


def register(sub):
    p = sub.add_parser('set-product')
    p.add_argument('project'); p.add_argument('--model', required=True)
    p.set_defaults(func=set_product)
    p = sub.add_parser('workflow')
    p.add_argument('project'); p.add_argument('--stage', choices=['status', 'plan', 'apply', 'preview', 'final'], default='status')
    p.add_argument('--database')
    def dispatch(args):
        if args.stage == 'plan' and not args.database:
            raise ValueError('规划需要 --database')
        flow(args)
    p.set_defaults(func=dispatch)
