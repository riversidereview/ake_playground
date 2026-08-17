export type SessionUser = {
  id: string;
  email: string;
  nickname: string;
};

export type SessionState = {
  authenticated: boolean;
  user?: SessionUser;
};

