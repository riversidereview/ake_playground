import { LoginForm } from "../../features/auth/login-form";

export default function LoginPage() {
  return (
    <div className="auth-layout">
      <section className="panel panel-muted" style={{ display: "grid", gap: 16 }}>
        <div className="eyebrow">账号系统</div>
        <div>
          <h1 style={{ margin: "0 0 10px" }}>登录终末地战斗日志</h1>
          <p className="muted" style={{ margin: 0 }}>
            网站现在统一使用邮箱和密码登录。普通用户登录后进入自己的管理页，管理员账号会直接进入全局控制后台。
          </p>
        </div>

        <div className="auth-steps">
          <div className="auth-step">
            <strong>1. 注册账号</strong>
            <span className="muted">首次使用时填写邮箱、公开昵称和密码，并通过邮箱验证码确认。</span>
          </div>
          <div className="auth-step">
            <strong>2. 邮箱密码登录</strong>
            <span className="muted">后续直接用邮箱和密码进入站点，验证码只用于新账号注册。</span>
          </div>
          <div className="auth-step">
            <strong>3. 进入管理页</strong>
            <span className="muted">普通账号登录后会直接进入“管理”，管理员则自动跳到后台。</span>
          </div>
        </div>

        <div className="panel-inset">
          <div className="eyebrow">当前说明</div>
          <div className="info-list" style={{ marginTop: 10 }}>
            <span>网站注册需要先获取邮箱验证码，再提交昵称和密码创建账号。</span>
            <span>公开昵称会继续用于榜单、战斗详情和分享摘要中的上传者显示。</span>
            <span>登录后的普通账号可以在“管理”里查看并删除自己上传的 battle。</span>
          </div>
        </div>
      </section>

      <LoginForm />
    </div>
  );
}
