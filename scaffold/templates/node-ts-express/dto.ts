// {{中文描述}}请求/响应
// ⚠️ 校验库以活代码为准（zod / class-validator / joi）
import { z } from 'zod';

export const create{{ModuleName}}Schema = z.object({
  // TODO(需求): 按接口字段补全；错误消息用 i18n key 或约定文案
  name: z.string().min(1, '{{i18nKey}}.name.required'),
});

export const update{{ModuleName}}Schema = create{{ModuleName}}Schema.partial();

export type {{ModuleName}}DTO = z.infer<typeof create{{ModuleName}}Schema>;
