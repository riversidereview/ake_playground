import { spawn } from "node:child_process";

const [, , command, ...restArgs] = process.argv;

if (!command) {
  console.error("缺少 Next 命令参数。");
  process.exit(1);
}

const env = { ...process.env };

if (!process.env.VERCEL && !process.env.CI) {
  if (command === "build" || command === "start") {
    env.NEXT_DIST_DIR = env.NEXT_DIST_DIR || ".next-build";
  }
}

const nextCommand = ["next", command, ...restArgs].join(" ");

const child = spawn(nextCommand, {
  stdio: "inherit",
  shell: true,
  env,
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
