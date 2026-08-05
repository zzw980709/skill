// {{中文描述}}路由
// ⚠️ 挂载位置与既有路由保持一致（如 app.ts 里 app.use('/{{mapping}}', {{moduleName}}Router)）
import { Router } from 'express';
import { {{ModuleName}}Service } from './{{moduleName}}.service';
import { create{{ModuleName}}Schema, update{{ModuleName}}Schema } from './{{moduleName}}.dto';
// ⚠️ 校验中间件以活代码为准（无则内联校验）
import { validate } from '../middlewares/validate';

const router = Router();

// TODO(需求): 依赖注入方式以活代码为准（构造器注入 / 容器 / 手动 new）
const service = new {{ModuleName}}Service();

// 列表
router.get('/', async (_req, res, next) => {
  try {
    const items = await service.list();
    // ⚠️ 响应包装以活代码为准
    res.json({ data: items });
  } catch (e) {
    next(e);
  }
});

// 创建
router.post('/', validate(create{{ModuleName}}Schema), async (req, res, next) => {
  try {
    await service.create(req.body);
    res.status(201).json({ message: 'success' });
  } catch (e) {
    next(e);
  }
});

// 更新
router.put('/:id', validate(update{{ModuleName}}Schema), async (req, res, next) => {
  try {
    await service.update(req.params.id, req.body);
    res.json({ message: 'success' });
  } catch (e) {
    next(e);
  }
});

// 删除
router.delete('/:id', async (req, res, next) => {
  try {
    await service.delete(req.params.id);
    res.json({ message: 'success' });
  } catch (e) {
    next(e);
  }
});

export const {{moduleName}}Router = router;
