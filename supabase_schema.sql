-- ============================================================
-- 대기배출시설 운영기록부 - Supabase 스키마
-- Supabase 대시보드 > SQL 에디터에서 순서대로 실행하세요.
-- ============================================================

-- 1. 테이블 생성
CREATE TABLE IF NOT EXISTS meter_readings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    reading_date        DATE NOT NULL,

    dong_bunche_power   NUMERIC(14,2),
    dong_bunche_volume  NUMERIC(14,2),
    dong_aekche_power   NUMERIC(14,2),
    dong_aekche_volume  NUMERIC(14,2),
    dong_pimak_power    NUMERIC(14,2),
    dong_pimak_volume   NUMERIC(14,2),
    sin_aekche_power    NUMERIC(14,2),
    sin_aekche_volume   NUMERIC(14,2),
    sin_yeonma_power    NUMERIC(14,2),
    sin_yeonma_volume   NUMERIC(14,2),
    sin_syote_power     NUMERIC(14,2),
    sin_syote_volume    NUMERIC(14,2),

    is_interpolated     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 소프트 삭제용 컬럼
    deleted_at          TIMESTAMPTZ,
    delete_batch_id     UUID,

    UNIQUE (user_id, reading_date)
);

-- 2. 인덱스
CREATE INDEX IF NOT EXISTS idx_readings_user_date
    ON meter_readings (user_id, reading_date);
CREATE INDEX IF NOT EXISTS idx_readings_batch
    ON meter_readings (delete_batch_id)
    WHERE delete_batch_id IS NOT NULL;

-- 3. Row Level Security
ALTER TABLE meter_readings ENABLE ROW LEVEL SECURITY;

-- 활성(삭제되지 않은) 데이터만 조회 가능 — 소프트 삭제 행은 자동으로 숨겨짐
CREATE POLICY "select_own_active" ON meter_readings
    FOR SELECT USING (auth.uid() = user_id AND deleted_at IS NULL);

-- 자신의 데이터만 삽입
CREATE POLICY "insert_own" ON meter_readings
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- 자신의 데이터만 수정 (소프트 삭제 포함)
CREATE POLICY "update_own" ON meter_readings
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 자신의 데이터만 영구 삭제 (단일 행 삭제)
CREATE POLICY "delete_own" ON meter_readings
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================================
-- 4. 소프트 삭제 RPC 함수
--    SELECT RLS가 deleted_at IS NULL 조건으로 숨긴 행에 접근하기 위해
--    SECURITY DEFINER를 사용합니다. auth.uid()로 소유권을 검증합니다.
-- ============================================================

-- 4-1. 삭제 배치 메타데이터 조회 (12시간 이내인 경우만 반환)
CREATE OR REPLACE FUNCTION get_pending_delete_meta(p_batch_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid        UUID := auth.uid();
    v_count      INT;
    v_deleted_at TIMESTAMPTZ;
BEGIN
    SELECT COUNT(*), MIN(deleted_at)
    INTO v_count, v_deleted_at
    FROM meter_readings
    WHERE delete_batch_id = p_batch_id
      AND user_id = v_uid
      AND deleted_at IS NOT NULL;

    IF v_count = 0 OR v_deleted_at < NOW() - INTERVAL '12 hours' THEN
        RETURN NULL;
    END IF;

    RETURN json_build_object(
        'batch_id',   p_batch_id,
        'count',      v_count,
        'deleted_at', v_deleted_at,
        'expires_at', v_deleted_at + INTERVAL '12 hours'
    );
END;
$$;

-- 4-2. 삭제 배치 복원 (12시간 이내인 경우만), 복원된 행 수 반환
CREATE OR REPLACE FUNCTION restore_delete_batch(p_batch_id UUID)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid        UUID := auth.uid();
    v_deleted_at TIMESTAMPTZ;
    v_count      INT;
BEGIN
    SELECT MIN(deleted_at)
    INTO v_deleted_at
    FROM meter_readings
    WHERE delete_batch_id = p_batch_id
      AND user_id = v_uid;

    IF v_deleted_at IS NULL OR v_deleted_at < NOW() - INTERVAL '12 hours' THEN
        RETURN 0;
    END IF;

    UPDATE meter_readings
    SET deleted_at = NULL,
        delete_batch_id = NULL
    WHERE delete_batch_id = p_batch_id
      AND user_id = v_uid;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
