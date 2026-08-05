// {{中文描述}}服务
import { {{ModuleName}}Repository } from './{{moduleName}}.repository';
// ⚠️ 模型类型来源以活代码为准：Prisma client / TypeORM entity / 手写 interface
import { {{ModuleName}} } from '@prisma/client';
// ⚠️ 错误类以活代码为准（ApiError / AppError / 直接 throw + 全局 errorHandler）
import { ApiError } from '../errors/api-error';

export class {{ModuleName}}Service {
  // TODO(需求): 注入方式以活代码为准
  private repo = new {{ModuleName}}Repository();

  async list(): Promise<{{ModuleName}}[]> {
    return this.repo.findAll();
  }

  async create(data: unknown): Promise<{{ModuleName}}> {
    // TODO(需求): 幂等/唯一性校验，命中时抛 ApiError(409, '{{i18nKey}}.exists')
    // TODO(需求): 若跨表写，用事务（Prisma $transaction / dataSource.transaction）
    return this.repo.create(data);
  }

  async update(id: string, data: unknown): Promise<{{ModuleName}}> {
    const entity = await this.repo.findById(id);
    if (!entity) {
      throw new ApiError(404, '{{i18nKey}}.not_found');
    }
    // TODO(需求): 字段映射 / 空值保留约定
    return this.repo.update(id, data);
  }

  async delete(id: string): Promise<void> {
    await this.repo.softDelete(id); // ⚠️ 是否软删除以活代码为准
  }
}
