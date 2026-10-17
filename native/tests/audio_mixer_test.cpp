#include "audio_mixer.h"
#include <cassert>
#include <cmath>
#include <iostream>

int main() {
    AudioMixer mixer(2, 4800);
    float first[] = {0.1f, 0.2f, 0.1f, 0.2f};
    float second[] = {0.3f, 0.4f, 0.3f, 0.4f};
    mixer.push(10, first, 2);
    mixer.push(20, second, 2);
    float output[4] = {};
    mixer.mix(output, 2);
    assert(std::abs(output[0] - 0.4f) < 0.00001f);
    assert(std::abs(output[1] - 0.6f) < 0.00001f);
    mixer.mix(output, 2);
    assert(output[0] == 0 && output[1] == 0); // no replay / duplicate
    std::vector<float> large(20000, 0.2f);
    for (int index = 0; index != 100; ++index) mixer.push(10, large.data(), 10000);
    assert(mixer.queued_frames() <= 4800);
    assert(mixer.overflows() > 0);
    mixer.clear();
    assert(mixer.queued_frames() == 0);
    mixer.mix(output, 2);
    assert(output[0] == 0);
    mixer.push(10, first, 2);
    mixer.push(20, second, 2);
    mixer.remove(10);
    mixer.mix(output, 2);
    assert(std::abs(output[0] - 0.3f) < 0.00001f);
    assert(std::abs(output[1] - 0.4f) < 0.00001f);
    std::cout << "audio mixer tests passed\n";
}
