"""第一层流水线：S1 -> S2"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1_course_agent import CourseAgent
from s2_translate_agent import TranslateAgent

def run_layer1(task_id, ppt_file, script_file, target_language='English'):
    print(f'[Layer1] Task: {task_id}')
    s1 = CourseAgent()
    s1_result = s1.run(task_id, ppt_file, script_file)
    print(f'[Layer1] S1 done: {s1_result["page_count"]} pages')
    s2 = TranslateAgent()
    s2_result = s2.run(task_id, s1_result['structured_json'], target_language)
    print(f'[Layer1] S2 done')
    return {'task_id': task_id, 's1_output': s1_result['structured_json'], 's2_output': s2_result['output_json']}

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--task_id', default='test_task')
    p.add_argument('--ppt', required=True)
    p.add_argument('--script', required=True)
    p.add_argument('--target', default='English')
    args = p.parse_args()
    print(run_layer1(args.task_id, args.ppt, args.script, args.target))
