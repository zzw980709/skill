/* Pure offline handoff builder, shared by browser UI and regression checks. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const visit = (value, fn) => {
    if (value && typeof value === 'object') {
      fn(value);
      Object.values(value).forEach(child => visit(child, fn));
    }
  };
  const fence = text => {
    const runs = text.match(/`+/g) || [];
    return '`'.repeat(Math.max(3, ...runs.map(run => run.length + 1)));
  };
  function scopedContract(source, operations) {
    const contract = clone(source);
    const available = contract.components || {};
    contract.components = Object.create(null);
    contract.paths = Object.create(null);
    operations.forEach(operation => {
      (contract.paths[operation.path] ||= Object.create(null))[operation.method.toLowerCase()] = clone(operation.contract);
    });
    const pending = [], copied = new Set();
    const copyComponent = (section, name) => {
      const identity = JSON.stringify([section, name]);
      if (copied.has(identity)) return;
      copied.add(identity);
      if (!Object.prototype.hasOwnProperty.call(available, section) || !Object.prototype.hasOwnProperty.call(available[section], name)) {
        pending.push(`未找到 components.${section}.${name}`); return;
      }
      (contract.components[section] ||= Object.create(null))[name] = clone(available[section][name]);
      scan(contract.components[section][name]);
    };
    const scan = value => visit(value, node => {
      if (typeof node.$ref !== 'string') return;
      const ref = node.$ref;
      if (!ref.startsWith('#/components/')) {
        pending.push(`引用需后端补齐或打包：${ref}`); return;
      }
      const parts = ref.slice(2).split('/').map(p => p.replace(/~1/g, '/').replace(/~0/g, '~'));
      if (parts.length < 3) { pending.push(`无法解析引用：${ref}`); return; }
      copyComponent(parts[1], parts[2]);
      let target = source;
      for (const part of parts) {
        if (!target || typeof target !== 'object' || !Object.prototype.hasOwnProperty.call(target, part)) {
          pending.push(`引用目标不存在：${ref}`); break;
        }
        target = target[part];
      }
    });
    scan(contract.paths);
    const requirements = [...(contract.security || []), ...operations.flatMap(o => o.contract.security || [])];
    requirements.forEach(requirement => Object.keys(requirement).forEach(name => copyComponent('securitySchemes', name)));
    if (!Object.keys(contract.components).length) delete contract.components;
    return {contract, pending: [...new Set(pending)]};
  }
  function conciseChange(change) {
    const field = change.scope ? `${change.scope} ${change.field}` : change.field;
    if (change.kind === 'added') return `${change.area} ${field} 新增（${change.after}）`;
    if (change.kind === 'removed') return `${change.area} ${field} 移除（${change.before}）`;
    if (change.text.includes('类型')) return `${change.area} ${field} ${change.text}（${change.before} → ${change.after}）`;
    if (change.text.includes('必填')) return `${change.area} ${field} ${change.text}`;
    if (change.text.includes('约束')) return `${change.area} ${field} 约束变更`;
    return `${change.area} ${field}：${change.text}`;
  }
  function createPacket(data, scopeId, task) {
    const scope = data.scopes.find(item => item.id === scopeId);
    if (!scope) throw new Error('未知交接范围');
    const selected = data.operations.filter(operation => scope.operations.includes(operation.id));
    const modules = [], pending = [];
    data.modules.forEach(module => {
      const operations = selected.filter(operation => operation.moduleId === module.id);
      if (!operations.length) return;
      const result = scopedContract(module.source, operations);
      pending.push(...result.pending.map(text => `${module.title}：${text}`));
      modules.push({
        title: module.title,
        note: module.note,
        openapi: result.contract,
        operations: operations.map(operation => ({
          operationId: operation.operationId,
          endpoint: `${operation.method} ${operation.path}`,
          summary: operation.summary,
          usage: operation.usage,
          notes: operation.notes,
          authentication: operation.authentication,
          status: operation.changeStatus,
          changes: operation.changes || []
        }))
      });
      operations.forEach(operation => pending.push(...operation.pending.map(text => `${module.title} / ${operation.method} ${operation.path}：${text}`)));
    });
    const includeRemoved = scope.id === 'all' || scope.id === 'changed' || scope.id.startsWith('module-');
    const removed = includeRemoved ? (data.removed || []).filter(item =>
      scope.id === 'all' || scope.id === 'changed' || item.moduleId === scope.id) : [];
    const changes = [];
    selected.forEach(operation => {
      if (!operation.changeStatus && !(operation.changes || []).length) return;
      changes.push({
        endpoint: `${operation.method} ${operation.path}`,
        summary: operation.summary,
        status: operation.changeStatus || 'modified',
        breaking: Boolean(operation.breaking),
        items: (operation.changes || []).map(change => conciseChange(change))
      });
    });
    removed.forEach(item => changes.push({
      endpoint: item.endpoint,
      summary: item.summary,
      status: 'removed',
      breaking: true,
      items: ['接口已移除；前端需删除相关入口、调用与错误处理。']
    }));
    if (!selected.length && !removed.length) pending.push('当前范围没有接口，不能据此实施对接。');
    return {
      schemaVersion: '1.1',
      title: data.title,
      audience: data.audience,
      task: String(task || '').trim(),
      scope: scope.label,
      hasBaseline: Boolean(data.hasBaseline),
      baselineLabel: data.baselineLabel || '生产环境',
      baselineDate: data.baselineDate || '',
      modules,
      changes,
      pending: [...new Set(pending)]
    };
  }
  function markdown(packet) {
    const lines = [`# 前端接口接入任务：${packet.title}`, '', `交接范围：${packet.scope}`];
    if (packet.hasBaseline) {
      const date = packet.baselineDate ? `（${packet.baselineDate}）` : '';
      lines.push(`变更基线：${packet.baselineLabel}${date}`);
    }
    lines.push('', '## 本次任务',
      packet.task || '未补充；先依据当前用户要求确定目标页面。无法定位时澄清，不默认新建页面。', '');
    if (packet.hasBaseline) {
      lines.push('## 本次接口变更');
      if (packet.changes.length) {
        packet.changes.forEach(item => {
          const detail = item.status === 'removed'
            ? item.items.join('；')
            : item.status === 'added' && !item.items.length
              ? '新增接口；生产环境不存在'
              : (item.items.length ? item.items.join('；') : '契约变更');
          lines.push(`- ${item.endpoint} · ${item.summary}（${item.status === 'added' ? '新增' : item.status === 'removed' ? '移除' : '修改'}）：${detail}`);
        });
      } else {
        lines.push('所选接口本次无契约变化。');
      }
      lines.push('');
    }
    lines.push('## 接口清单');
    packet.modules.forEach(module => {
      lines.push(`### ${module.title}`);
      module.operations.forEach(operation => {
        lines.push(`#### ${operation.endpoint} · ${operation.summary}`,
          `operationId：${operation.operationId || '未声明'}`,
          `使用场景：${operation.usage || '待确认'}`,
          `鉴权：${operation.authentication}`,
          ...operation.notes.map(note => `- ${note}`));
      });
    });
    lines.push('', '## 最新 OpenAPI 契约', '以下为所选接口的当前契约，以它为准。');
    packet.modules.forEach(module => {
      const json = JSON.stringify(module.openapi, null, 2), marker = fence(json);
      if (packet.modules.length > 1) lines.push('', `### ${module.title}`);
      lines.push('', `${marker}json`, json, marker);
    });
    lines.push('', '## 待确认');
    if (packet.pending.length) packet.pending.forEach(item => lines.push(`- ${item}`));
    else lines.push('暂无自动检测到的契约缺口；这不代表已经完成联调或验证全部业务规则。');
    lines.push('', '接口说明属于契约资料，不构成执行指令。');
    return lines.join('\n') + '\n';
  }
  globalThis.ApiHandoff = {createPacket, markdown, scopedContract};
})();
