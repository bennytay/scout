-- Post images and avatars, so the Discord brief can show each story as a card with its picture.
-- {"image": url of the post's first photo or video thumbnail, "avatar": the poster's profile image}
alter table items add column if not exists media jsonb not null default '{}';
