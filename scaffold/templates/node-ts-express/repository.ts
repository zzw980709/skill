// {{中文描述}}数据访问
// ⚠️ ORM 以活代码为准：Prisma / TypeORM / Knex / Sequelize…
import { prisma } from '../lib/prisma';

export class {{ModuleName}}Repository {
  findAll() {
    return prisma.{{moduleName}}.findMany({ where: { deleted: false } });
  }

  findById(id: string) {
    return prisma.{{moduleName}}.findFirst({ where: { id, deleted: false } });
  }

  create(data: unknown) {
    return prisma.{{moduleName}}.create({ data });
  }

  update(id: string, data: unknown) {
    return prisma.{{moduleName}}.update({ where: { id }, data });
  }

  // 软删除：deleted 字段约定以活代码为准；若用硬删除直接 delete
  softDelete(id: string) {
    return prisma.{{moduleName}}.update({ where: { id }, data: { deleted: true, deletedAt: new Date() } });
  }
}
